import asyncio
import logging
import os
import stat
import time
from typing import Any, AsyncIterator, List, Optional

import asyncssh
import inspect

from dcfs.app.utils import normalize_global_path, split_global_path
from dcfs.core import Clients, Ops
from dcfs.errors import FileOrDirectoryDoesNotExist

logger = logging.getLogger(__name__)

class DCFSSFTPHandler(asyncssh.SFTPServer):
    def __init__(self, clients: Clients, *args: Any, **kwargs: Any):
        self.clients = clients
        super().__init__(*args, **kwargs)

    def _get_ops(self, path_bytes: bytes) -> tuple[Optional[Ops], str]:
        path = path_bytes.decode("utf-8")
        if not path:
            return None, "/"

        try:
            path = normalize_global_path(path)
        except Exception:
            logger.debug(f"Failed to normalize global path: {path}")

        if path in (".", "/"):
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
                    names.append(asyncssh.SFTPName(client_name.encode("utf-8")))
            return names

        if sub_path == "/":
            directory = ops._client.dir_api.root
        else:
            directory = ops.cd(sub_path)

        for d in directory.find_dirs():
            names.append(asyncssh.SFTPName(d.name.encode("utf-8")))
        for f in directory.find_files():
            names.append(asyncssh.SFTPName(f.name.encode("utf-8")))

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

    async def open(self, path: bytes, flags: int, attrs: asyncssh.SFTPAttrs) -> 'DCFSSFTPFileBase':  # type: ignore[override]
        ops, sub_path = self._get_ops(path)
        if ops is None:
            raise asyncssh.SFTPPermissionDenied("Cannot open root or client directory")

        mode = ""
        if flags & asyncssh.FXF_WRITE:
             mode = "w"
        else:
            mode = "r"

        expected_size: Optional[int] = None
        if getattr(attrs, "size", None) is not None:
            try:
                expected_size = int(attrs.size)  # type: ignore[arg-type]
            except Exception:
                expected_size = None
            if expected_size is not None and expected_size < 0:
                expected_size = None

        if mode == "w" and expected_size is not None:
            return DCFSSFTPStreamingFile(ops, sub_path, expected_size)
        return DCFSSFTPBufferedFile(ops, sub_path, mode)

    async def read(self, file_obj: object, offset: int, size: int) -> bytes:  # type: ignore[override]
        if isinstance(file_obj, DCFSSFTPFileBase):
            return await file_obj.read(offset, size)
        result = super().read(file_obj, offset, size)  # type: ignore[misc]
        if inspect.isawaitable(result):
            return await result
        return result

    async def write(self, file_obj: object, offset: int, data: bytes) -> int:  # type: ignore[override]
        if isinstance(file_obj, DCFSSFTPFileBase):
            return await file_obj.write(offset, data)
        result = super().write(file_obj, offset, data)  # type: ignore[misc]
        if inspect.isawaitable(result):
            return await result
        return result

    async def close(self, file_obj: object) -> None:  # type: ignore[override]
        if isinstance(file_obj, DCFSSFTPFileBase):
            await file_obj.close()
            return
        result = super().close(file_obj)
        if inspect.isawaitable(result):
            await result

    async def fstat(self, file_obj: object) -> asyncssh.SFTPAttrs:  # type: ignore[override]
        if isinstance(file_obj, DCFSSFTPFileBase):
            return await file_obj.fstat()

        result = super().fstat(file_obj)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, os.stat_result):
            return asyncssh.SFTPAttrs.from_local(result)
        return result

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
        try:
            normalized = normalize_global_path(path.decode("utf-8"))
            return normalized.encode("utf-8")
        except Exception:
            return b"/" + path.lstrip(b"/")

class DCFSSFTPFileBase:
    async def read(self, offset: int, size: int) -> bytes:
        raise NotImplementedError

    async def write(self, offset: int, data: bytes) -> int:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def fstat(self) -> asyncssh.SFTPAttrs:
        raise NotImplementedError


class DCFSSFTPBufferedFile(DCFSSFTPFileBase):
    def __init__(self, ops: Ops, path: str, mode: str):
        self.ops = ops
        self.path = path
        self.mode = mode
        self.buffer = bytearray()
        self.closed = False

    async def read(self, offset: int, size: int) -> bytes:
        if "r" not in self.mode:
            raise asyncssh.SFTPPermissionDenied("File not open for reading")

        end = -1 if size < 0 else offset + size - 1
        stream = await self.ops.download(
            self.path,
            offset,
            end,
            os.path.basename(self.path),
        )
        data = bytearray()
        async for chunk in stream:
            data.extend(chunk)
        return bytes(data)

    async def write(self, offset: int, data: bytes) -> int:
        if "w" not in self.mode:
            raise asyncssh.SFTPPermissionDenied("File not open for writing")

        if offset > len(self.buffer):
            self.buffer.extend(b"\x00" * (offset - len(self.buffer)))

        end = offset + len(data)
        if end <= len(self.buffer):
            self.buffer[offset:end] = data
        else:
            if offset < len(self.buffer):
                self.buffer[offset:] = data
            else:
                self.buffer.extend(data)

        return len(data)

    async def close(self) -> None:
        if self.closed:
            return

        if "w" in self.mode:
            await self.ops.upload_from_bytes(bytes(self.buffer), self.path)

        self.closed = True

    async def fstat(self) -> asyncssh.SFTPAttrs:
        if "w" in self.mode:
            now = int(time.time())
            return asyncssh.SFTPAttrs(
                mode=stat.S_IFREG | 0o644,
                size=len(self.buffer),
                mtime=now,
                atime=now,
            )

        fd = await self.ops.desc(self.path, validate=False)
        fv = fd.get_latest_version()
        size = await self.ops._client.fc_repo.content_length(fv)
        mtime = int(fv.updated_at_timestamp / 1000)
        return asyncssh.SFTPAttrs(
            mode=stat.S_IFREG | 0o644,
            size=size,
            mtime=mtime,
            atime=mtime,
        )


class DCFSSFTPStreamingFile(DCFSSFTPFileBase):
    def __init__(self, ops: Ops, path: str, expected_size: int):
        self.ops = ops
        self.path = path
        self.expected_size = expected_size
        self.closed = False

        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=32)
        self._pending: dict[int, bytes] = {}
        self._next_offset = 0
        self._upload_task = asyncio.create_task(self._run_upload())

    async def _stream(self) -> AsyncIterator[bytes]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            if item:
                yield item

    async def _run_upload(self) -> None:
        await self.ops.upload_from_stream(self._stream(), self.expected_size, self.path)

    async def read(self, offset: int, size: int) -> bytes:
        raise asyncssh.SFTPOpUnsupported("Streaming file handle does not support reads")

    async def write(self, offset: int, data: bytes) -> int:
        if self.closed:
            raise asyncssh.SFTPFailure("File already closed")

        if offset < 0:
            raise asyncssh.SFTPFailure("Invalid offset")

        if not data:
            return 0

        end = offset + len(data)
        if end > self.expected_size:
            raise asyncssh.SFTPFailure("Write exceeds expected file size")

        existing = self._pending.get(offset)
        if existing is not None and existing != data:
            raise asyncssh.SFTPFailure("Overlapping writes are not supported")

        self._pending[offset] = data

        while True:
            chunk = self._pending.pop(self._next_offset, None)
            if chunk is None:
                break
            await self._queue.put(chunk)
            self._next_offset += len(chunk)

        return len(data)

    async def close(self) -> None:
        if self.closed:
            return

        self.closed = True

        if self._next_offset != self.expected_size:
            raise asyncssh.SFTPFailure(
                f"Upload incomplete: received {self._next_offset} of {self.expected_size} bytes"
            )

        await self._queue.put(None)
        await self._upload_task

    async def fstat(self) -> asyncssh.SFTPAttrs:
        now = int(time.time())
        return asyncssh.SFTPAttrs(
            mode=stat.S_IFREG | 0o644,
            size=self.expected_size,
            mtime=now,
            atime=now,
        )
