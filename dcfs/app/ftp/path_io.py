import asyncio
import logging
import os
import pathlib
import stat
from typing import AsyncIterator, Optional

import aioftp

from dcfs.app.utils import normalize_global_path, split_global_path
from dcfs.config import get_config
from dcfs.core import Clients, Ops
from dcfs.errors import FileOrDirectoryDoesNotExist
from dcfs.utils.retry import _is_transient

logger = logging.getLogger(__name__)


class DCFSPathIO(aioftp.AbstractPathIO):
    def __init__(self, clients: Clients):
        super().__init__()
        self.clients = clients

    def _get_ops(self, path: pathlib.PurePosixPath) -> tuple[Optional[Ops], str]:
        path_str = str(path)
        if not path_str:
            return None, "/"

        try:
            path_str = normalize_global_path(path_str)
        except Exception:
            logger.debug(f"Failed to normalize global path: {path_str}")

        if path_str in (".", "/"):
            return None, "/"

        try:
            client_name, sub_path = split_global_path(path_str)
            if client_name in self.clients:
                return Ops(self.clients[client_name]), "/" + sub_path.lstrip("/")
            raise FileNotFoundError(f"No such client: {client_name}")
        except FileNotFoundError:
            raise
        except Exception:
            logger.debug(f"Failed to split global path: {path_str}")
        return None, path_str

    async def exists(self, path: pathlib.PurePosixPath) -> bool:
        try:
            ops, sub_path = self._get_ops(path)
        except FileNotFoundError:
            return False

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
        try:
            ops, sub_path = self._get_ops(path)
        except FileNotFoundError:
            return False

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
        try:
            ops, sub_path = self._get_ops(path)
        except FileNotFoundError:
            return False

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
        try:
            ops, sub_path = self._get_ops(path)
        except FileNotFoundError:
            return

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
        self.pos = 0
        self.closed = False
        self._stream: Optional[AsyncIterator[bytes]] = None
        self._iter: Optional[AsyncIterator[bytes]] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def read(self, count: int = -1) -> bytes:
        if "r" not in self.mode:
            raise IOError("File not open for reading")

        if self._stream is None:
            self._stream = await self.ops.download(
                self.path, self.pos, -1, os.path.basename(self.path), validate=False
            )
            self._iter = self._stream.__aiter__()

        if count == -1:
            res = self.buffer
            self.buffer = bytearray()
            async for chunk in self._stream:
                res.extend(chunk)
            self.pos += len(res)
            return bytes(res)

        while len(self.buffer) < count:
            try:
                if self._iter is None:
                    break
                chunk = await anext(self._iter)
                self.buffer.extend(chunk)
            except StopAsyncIteration:
                break

        res = self.buffer[:count]
        self.buffer = self.buffer[count:]
        self.pos += len(res)
        return bytes(res)

    async def write(self, data: bytes) -> int:
        if "w" not in self.mode and "a" not in self.mode:
            raise IOError("File not open for writing")
        self.buffer.extend(data)
        self.pos += len(data)
        return len(data)

    async def close(self) -> None:
        if self.closed:
            return

        if ("w" in self.mode or "a" in self.mode) and self.buffer:
            data = bytes(self.buffer)
            self.buffer.clear()

            cfg = get_config().dcfs.download
            max_retries = cfg.upload_max_retries
            base_delay = cfg.upload_base_retry_delay

            last_ex: Optional[Exception] = None
            for attempt in range(max_retries):
                try:
                    await self.ops.upload_from_bytes(data, self.path)
                    return
                except Exception as ex:
                    last_ex = ex
                    if not _is_transient(ex):
                        logger.error(
                            f"Permanent upload failure for {self.path}: {ex}"
                        )
                        raise

                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Transient upload failure for {self.path} ({ex}). "
                        f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            logger.error(
                f"Upload failed for {self.path} after {max_retries} retries: {last_ex}",
            )
            raise last_ex  # type: ignore[misc]

        self.closed = True

    async def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            if offset != self.pos:
                self._stream = None
                self._iter = None
                self.buffer = bytearray()
                self.pos = offset
            return self.pos
        elif whence == os.SEEK_CUR:
            # We don't support moving CUR except by 0 for now to keep it simple,
            # but usually it's used with 0 to get current pos.
            self.pos += offset
            if offset != 0:
                self._stream = None
                self._iter = None
                self.buffer = bytearray()
            return self.pos

        raise NotImplementedError(f"Seek whence {whence} not supported")
