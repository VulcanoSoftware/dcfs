import asyncio
import logging
import os
import time
from typing import Optional

from dcfs.app.utils import split_global_path
from dcfs.core import Clients, Ops
from dcfs.errors import FileOrDirectoryDoesNotExist

logger = logging.getLogger(__name__)

SMB_ST_MODE_DIR = 0x10
SMB_ST_MODE_REG = 0x20

class DCFSSMBStorage:
    def __init__(self, clients: Clients, loop: asyncio.AbstractEventLoop):
        self.clients = clients
        self.loop = loop

    def _get_ops(self, path: str) -> tuple[Optional[Ops], str]:
        path = path.replace("\\", "/")
        if not path or path == "/" or path == ".":
            return None, "/"

        try:
            client_name, sub_path = split_global_path(path)
            if client_name in self.clients:
                return Ops(self.clients[client_name]), "/" + sub_path.lstrip("/")
        except Exception:
             logger.debug(f"Failed to split global path: {path}")
        return None, path

    def listPath(self, path: str, filter: str = "*"):
        ops, sub_path = self._get_ops(path)
        results = []

        if ops is None:
            if sub_path == "/":
                for client_name in self.clients:
                     results.append(self._make_stat(client_name, is_dir=True))
            return results

        if sub_path == "/":
            directory = ops._client.dir_api.root
        else:
            try:
                directory = ops.cd(sub_path)
            except FileOrDirectoryDoesNotExist:
                return []

        for d in directory.find_dirs():
            results.append(self._make_stat(d.name, is_dir=True, mtime=d.modified_at_timestamp/1000))
        for f in directory.find_files():
            results.append(self._make_stat(f.name, is_dir=False))

        return results

    def _make_stat(self, name, is_dir=False, size=0, mtime=None):
        if mtime is None:
            mtime = time.time()

        class SMBStat:
            def __init__(self, name, is_dir, size, mtime):
                self.name = name
                self.st_mode = SMB_ST_MODE_DIR if is_dir else SMB_ST_MODE_REG
                self.st_size = size
                self.st_mtime = mtime
                self.st_atime = mtime
                self.st_ctime = mtime
                self.st_ishidden = False
                self.st_isreadonly = False

        return SMBStat(name, is_dir, size, mtime)

    def getFileStat(self, path: str):
        ops, sub_path = self._get_ops(path)
        if ops is None or sub_path == "/":
            return self._make_stat(os.path.basename(path) or "/", is_dir=True)

        try:
            directory = ops.cd(sub_path)
            return self._make_stat(os.path.basename(path), is_dir=True, mtime=directory.modified_at_timestamp/1000)
        except FileOrDirectoryDoesNotExist:
            try:
                async def _get_file_stat():
                    fd = await ops.desc(sub_path, validate=False)
                    fv = fd.get_latest_version()
                    size = await ops._client.fc_repo.content_length(fv)
                    return size, fv.updated_at_timestamp/1000

                future = asyncio.run_coroutine_threadsafe(_get_file_stat(), self.loop)
                size, mtime = future.result()
                return self._make_stat(os.path.basename(path), is_dir=False, size=size, mtime=mtime)
            except Exception:
                 raise OSError(f"File not found: {path}")

    def openFile(self, path: str, mode: str):
        ops, sub_path = self._get_ops(path)
        if ops is None:
             raise OSError("Cannot open root")
        return DCFSSMBFile(ops, sub_path, mode, self.loop)

    def mkdir(self, path: str):
        ops, sub_path = self._get_ops(path)
        if ops:
            future = asyncio.run_coroutine_threadsafe(ops.mkdir(sub_path, parents=False), self.loop)
            future.result()

    def rmdir(self, path: str):
        ops, sub_path = self._get_ops(path)
        if ops:
             future = asyncio.run_coroutine_threadsafe(ops.rm_dir(sub_path, recursive=False), self.loop)
             future.result()

    def deleteFile(self, path: str):
        ops, sub_path = self._get_ops(path)
        if ops:
             future = asyncio.run_coroutine_threadsafe(ops.rm_file(sub_path), self.loop)
             future.result()

    def rename(self, oldpath: str, newpath: str):
         ops_src, sub_src = self._get_ops(oldpath)
         ops_dst, sub_dst = self._get_ops(newpath)
         if ops_src and ops_dst and ops_src._client == ops_dst._client:
             async def _rename():
                 try:
                     await ops_src.mv_file(sub_src, sub_dst)
                 except Exception:
                     await ops_src.mv_dir(sub_src, sub_dst)

             future = asyncio.run_coroutine_threadsafe(_rename(), self.loop)
             future.result()

class DCFSSMBFile:
    def __init__(self, ops: Ops, path: str, mode: str, loop: asyncio.AbstractEventLoop):
        self.ops = ops
        self.path = path
        self.mode = mode
        self.loop = loop
        self.pos = 0
        self.buffer = bytearray()

    def read(self, size: int, offset: int):
        if size <= 0:
            return b""

        async def _read():
            # end is inclusive in ops.download
            stream = await self.ops.download(
                self.path, offset, offset + size - 1, os.path.basename(self.path)
            )
            data = b""
            async for chunk in stream:
                data += chunk
            return data

        future = asyncio.run_coroutine_threadsafe(_read(), self.loop)
        return future.result()

    def write(self, data: bytes, offset: int):
        if offset != self.pos:
             logger.warning(f"Random access write at {offset} when pos is {self.pos} for SMB.")

        self.buffer.extend(data)
        self.pos += len(data)
        return len(data)

    def close(self):
        if ("w" in self.mode or "a" in self.mode) and self.buffer:
             future = asyncio.run_coroutine_threadsafe(self.ops.upload_from_bytes(bytes(self.buffer), self.path), self.loop)
             future.result()
