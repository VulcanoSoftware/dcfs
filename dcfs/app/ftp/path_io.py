import asyncio
import os
import pathlib
import stat
from typing import AsyncIterator, Optional

import aioftp
from dcfs.app.utils import split_global_path
from dcfs.core import Clients, Ops
from dcfs.errors import FileOrDirectoryDoesNotExist


class DCFSPathIO(aioftp.AbstractPathIO):
    def __init__(self, clients: Clients):
        super().__init__()
        self.clients = clients

    def _get_ops(self, path: pathlib.PurePosixPath) -> tuple[Optional[Ops], str]:
        path_str = str(path)
        if path_str == "/" or path_str == ".":
            return None, "/"

        try:
            client_name, sub_path = split_global_path(path_str)
            if client_name in self.clients:
                return Ops(self.clients[client_name]), "/" + sub_path.lstrip("/")
        except Exception:
            pass
        return None, path_str

    async def exists(self, path: pathlib.PurePosixPath) -> bool:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            if sub_path == "/":
                return True
            client_name = sub_path.strip("/")
            return client_name in self.clients

        if sub_path == "/":
            return True

        try:
            # Try to see if it's a directory
            ops.cd(sub_path)
            return True
        except FileOrDirectoryDoesNotExist:
            try:
                ops.stat_file(sub_path)
                return True
            except FileOrDirectoryDoesNotExist:
                return False

    async def is_dir(self, path: pathlib.PurePosixPath) -> bool:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            return True  # Root or client root

        if sub_path == "/":
            return True

        try:
            ops.cd(sub_path)
            return True
        except FileOrDirectoryDoesNotExist:
            return False

    async def is_file(self, path: pathlib.PurePosixPath) -> bool:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            return False

        try:
            ops.stat_file(sub_path)
            return True
        except FileOrDirectoryDoesNotExist:
            return False

    async def mkdir(
        self,
        path: pathlib.PurePosixPath,
        *,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise PermissionError("Cannot create directory in root")
        try:
            await ops.mkdir(sub_path, parents)
        except Exception:
            if not exist_ok:
                raise

    async def rmdir(self, path: pathlib.PurePosixPath) -> None:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise PermissionError("Cannot remove client directory")
        await ops.rm_dir(sub_path, recursive=False)

    async def unlink(self, path: pathlib.PurePosixPath) -> None:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise PermissionError("Cannot unlink client directory")
        await ops.rm_file(sub_path)

    async def list(self, path: pathlib.PurePosixPath) -> AsyncIterator[pathlib.PurePosixPath]:
        ops, sub_path = self._get_ops(path)
        if ops is None:
            if sub_path == "/":
                for client_name in self.clients:
                    yield path / client_name
            return

        if sub_path == "/":
            directory = ops._client.dir_api.root
        else:
            directory = ops.cd(sub_path)

        for d in directory.find_dirs():
            yield path / d.name
        for f in directory.find_files():
            yield path / f.name

    async def stat(self, path: pathlib.PurePosixPath) -> os.stat_result:
        ops, sub_path = self._get_ops(path)

        mode = 0
        size = 0
        mtime = 0.0

        if ops is None or sub_path == "/":
            # Root or client root
            mode = stat.S_IFDIR | 0o755
        else:
            try:
                directory = ops.cd(sub_path)
                mode = stat.S_IFDIR | 0o755
                mtime = directory.modified_at_timestamp / 1000
            except FileOrDirectoryDoesNotExist:
                fd = await ops.desc(sub_path, validate=False)
                fv = fd.get_latest_version()
                size = await ops._client.fc_repo.content_length(fv)
                mode = stat.S_IFREG | 0o644
                mtime = fv.updated_at_timestamp / 1000

        return os.stat_result((mode, 0, 0, 0, 0, 0, size, mtime, mtime, mtime))

    async def _open(self, path: pathlib.PurePosixPath, mode: str) -> "DCFSFileIO":  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise PermissionError("Cannot open root or client directory")
        return DCFSFileIO(ops, sub_path, mode)

    async def read(self, file: "DCFSFileIO", block_size: int) -> bytes:  # type: ignore[override]
        return await file.read(block_size)

    async def write(self, file: "DCFSFileIO", data: bytes) -> int:  # type: ignore[override]
        await file.write(data)
        return len(data)

    async def seek(self, file: "DCFSFileIO", offset: int, whence: int = os.SEEK_SET) -> int:  # type: ignore[override]
        return await file.seek(offset, whence)

    async def close(self, file: "DCFSFileIO") -> None:  # type: ignore[override]
        await file.close()

    async def rename(self, source: pathlib.PurePosixPath, destination: pathlib.PurePosixPath) -> None:
        ops_src, sub_src = self._get_ops(source)
        ops_dst, sub_dst = self._get_ops(destination)

        if ops_src is None or ops_dst is None or ops_src._client != ops_dst._client:
             raise PermissionError("Cannot rename across clients")

        # Check if source is dir or file
        try:
            ops_src.cd(sub_src)
            await ops_src.mv_dir(sub_src, sub_dst)
        except FileOrDirectoryDoesNotExist:
            await ops_src.mv_file(sub_src, sub_dst)


class DCFSFileIO:
    def __init__(self, ops: Ops, path: str, mode: str):
        self.ops = ops
        self.path = path
        self.mode = mode
        self.buffer = bytearray()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def read(self, count: int = -1) -> bytes:
        if "r" not in self.mode:
            raise IOError("File not open for reading")

        # This is tricky because aioftp expects a seekable/readable file-like object
        # but our download is a stream.
        # For simplicity, if this is the first read, we might need to fetch the whole thing
        # or implement a better streaming reader.

        # Actually, aioftp's server uses `read` in a loop.
        # If we want to support streaming, we should probably keep an iterator.

        if not hasattr(self, "_stream"):
             self._stream = await self.ops.download(self.path, 0, -1, os.path.basename(self.path))
             self._iter = self._stream.__aiter__()

        if count == -1:
            res = self.buffer
            self.buffer = bytearray()
            async for chunk in self._stream:
                res.extend(chunk)
            return bytes(res)

        while len(self.buffer) < count:
            try:
                chunk = await anext(self._iter)
                self.buffer.extend(chunk)
            except StopAsyncIteration:
                break

        res = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return bytes(res)

    async def write(self, data: bytes) -> int:
        if "w" not in self.mode and "a" not in self.mode:
            raise IOError("File not open for writing")
        self.buffer.extend(data)
        return len(data)

    async def close(self) -> None:
        if self.closed:
            return
        if ("w" in self.mode or "a" in self.mode) and self.buffer:
            await self.ops.upload_from_bytes(bytes(self.buffer), self.path)
        self.closed = True

    async def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        # aioftp might use seek for resumes.
        # Implementing seek for our stream-based system is hard.
        # For now, let's just support SEEK_SET 0 or the end of current buffer.
        if whence == os.SEEK_SET and offset == 0:
            if hasattr(self, "_stream"):
                del self._stream
                del self._iter
            self.buffer = bytearray()
            return 0
        raise NotImplementedError("Seek only supported for 0")
