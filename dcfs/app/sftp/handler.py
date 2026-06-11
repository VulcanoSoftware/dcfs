import logging
import os
import stat
from typing import Any, List, Optional

import asyncssh

from dcfs.app.utils import split_global_path
from dcfs.core import Clients, Ops
from dcfs.errors import FileOrDirectoryDoesNotExist

logger = logging.getLogger(__name__)

class DCFSSFTPHandler(asyncssh.SFTPServer):
    def __init__(self, clients: Clients, *args: Any, **kwargs: Any):
        self.clients = clients
        super().__init__(*args, **kwargs)

    def _get_ops(self, path_bytes: bytes) -> tuple[Optional[Ops], str]:
        path = path_bytes.decode('utf-8')
        if path == "." or path == "/" or not path:
            return None, "/"

        try:
            client_name, sub_path = split_global_path(path)
            if client_name in self.clients:
                return Ops(self.clients[client_name]), "/" + sub_path.lstrip("/")
        except Exception:
            logger.debug(f"Failed to split global path: {path}")
        return None, path

    async def listdir(self, path: bytes) -> List[asyncssh.SFTPName]:  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        names = []

        if ops is None:
            if sub_path == "/":
                for client_name in self.clients:
                    names.append(asyncssh.SFTPName(client_name))
            return names

        if sub_path == "/":
            directory = ops._client.dir_api.root
        else:
            directory = ops.cd(sub_path)

        for d in directory.find_dirs():
            names.append(asyncssh.SFTPName(d.name))
        for f in directory.find_files():
            names.append(asyncssh.SFTPName(f.name))

        return names

    async def stat(self, path: bytes) -> asyncssh.SFTPAttrs:  # type: ignore[override]
        ops, sub_path = self._get_ops(path)

        mode = 0
        size = 0
        mtime = 0

        if ops is None or sub_path == "/":
            mode = stat.S_IFDIR | 0o755
        else:
            try:
                directory = ops.cd(sub_path)
                mode = stat.S_IFDIR | 0o755
                mtime = int(directory.modified_at_timestamp / 1000)
            except FileOrDirectoryDoesNotExist:
                try:
                    fd = await ops.desc(sub_path, validate=False)
                    fv = fd.get_latest_version()
                    size = await ops._client.fc_repo.content_length(fv)
                    mode = stat.S_IFREG | 0o644
                    mtime = int(fv.updated_at_timestamp / 1000)
                except FileOrDirectoryDoesNotExist:
                    raise asyncssh.SFTPNoSuchFile(f"No such file: {path.decode('utf-8')}")

        return asyncssh.SFTPAttrs(mode=mode, size=size, mtime=mtime, atime=mtime)

    async def open(self, path: bytes, flags: int, attrs: asyncssh.SFTPAttrs) -> 'DCFSSFTPFile':  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise asyncssh.SFTPPermissionDenied("Cannot open root or client directory")

        mode = ""
        if flags & asyncssh.FXF_WRITE:
             mode = "w"
        else:
            mode = "r"

        return DCFSSFTPFile(ops, sub_path, mode)

    async def mkdir(self, path: bytes, attrs: asyncssh.SFTPAttrs) -> None:  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise asyncssh.SFTPPermissionDenied("Cannot create directory in root")
        await ops.mkdir(sub_path, parents=False)

    async def rmdir(self, path: bytes) -> None:  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise asyncssh.SFTPPermissionDenied("Cannot remove client directory")
        await ops.rm_dir(sub_path, recursive=False)

    async def remove(self, path: bytes) -> None:  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise asyncssh.SFTPPermissionDenied("Cannot remove client directory")
        await ops.rm_file(sub_path)

    async def rename(self, oldpath: bytes, newpath: bytes) -> None:  # type: ignore[override]
        ops_src, sub_src = self._get_ops(oldpath)
        ops_dst, sub_dst = self._get_ops(newpath)

        if ops_src is None or ops_dst is None or ops_src._client != ops_dst._client:
             raise asyncssh.SFTPPermissionDenied("Cannot rename across clients")

        try:
            ops_src.cd(sub_src)
            await ops_src.mv_dir(sub_src, sub_dst)
        except FileOrDirectoryDoesNotExist:
            await ops_src.mv_file(sub_src, sub_dst)

    async def realpath(self, path: bytes) -> bytes:  # type: ignore[override]
        return b"/" + path.lstrip(b"/")

class DCFSSFTPFile:
    def __init__(self, ops: Ops, path: str, mode: str):
        self.ops = ops
        self.path = path
        self.mode = mode
        self.buffer = bytearray()
        self.pos = 0
        self.closed = False
        self._stream: Optional[Any] = None
        self._iter: Optional[Any] = None

    async def read(self, offset: int, size: int) -> bytes:
        if "r" not in self.mode:
            raise asyncssh.SFTPPermissionDenied("File not open for reading")

        if self._stream is None or offset != self.pos:
            # We don't support random access well, so we restart if offset changes
            self._stream = await self.ops.download(self.path, offset, -1, os.path.basename(self.path))
            self._iter = self._stream.__aiter__()
            self.buffer = bytearray()
            self.pos = offset

        while len(self.buffer) < size:
            try:
                if self._iter is None:
                     break
                chunk = await anext(self._iter)
                self.buffer.extend(chunk)
            except StopAsyncIteration:
                break

        data = self.buffer[:size]
        self.buffer = self.buffer[size:]
        self.pos += len(data)
        return bytes(data)

    async def write(self, offset: int, data: bytes) -> int:
        if "w" not in self.mode:
            raise asyncssh.SFTPPermissionDenied("File not open for writing")

        if offset != self.pos:
             logger.warning(f"Random access write at {offset} when pos is {self.pos}")

        self.buffer.extend(data)
        self.pos += len(data)
        return len(data)

    async def close(self) -> None:
        if self.closed:
            return

        if "w" in self.mode and self.buffer:
             await self.ops.upload_from_bytes(bytes(self.buffer), self.path)

        self.closed = True

    async def stat(self) -> asyncssh.SFTPAttrs:
        fd = await self.ops.desc(self.path, validate=False)
        fv = fd.get_latest_version()
        size = await self.ops._client.fc_repo.content_length(fv)
        mode = stat.S_IFREG | 0o644
        mtime = int(fv.updated_at_timestamp / 1000)
        return asyncssh.SFTPAttrs(mode=mode, size=size, mtime=mtime, atime=mtime)
