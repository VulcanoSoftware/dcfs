import asyncio
import logging
import os
import time
from typing import Optional

from dcfs.app.utils import normalize_global_path, split_global_path
from dcfs.config import get_config
from dcfs.core import Clients, Ops
from dcfs.errors import FileOrDirectoryDoesNotExist
from dcfs.utils.retry import _is_transient

logger = logging.getLogger(__name__)

SMB_ST_MODE_DIR = 0x10
SMB_ST_MODE_REG = 0x20

class DCFSSMBStorage:
    def __init__(self, clients: Clients, loop: asyncio.AbstractEventLoop):
        self.clients = clients
        self.loop = loop

    def _get_ops(self, path: str) -> tuple[Optional[Ops], str]:
        if not path:
            return None, "/"

        try:
            path = normalize_global_path(path)
        except Exception:
            path = path.replace("\\", "/")
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
        # Fetch file sizes in parallel via a single async task
        file_refs = list(directory.find_files())
        if file_refs:
            async def _fetch_sizes():
                tasks = []
                for fr in file_refs:
                    tasks.append(
                        asyncio.create_task(
                            self._file_size_for_ref(ops, sub_path, fr.name)
                        )
                    )
                return await asyncio.gather(*tasks)

            future = asyncio.run_coroutine_threadsafe(
                _fetch_sizes(), self.loop
            )
            try:
                sizes = future.result()
            except Exception as ex:
                logger.warning(f"Failed to fetch file sizes for listing: {ex}")
                sizes = [0] * len(file_refs)

            for fr, size in zip(file_refs, sizes):
                results.append(
                    self._make_stat(fr.name, is_dir=False, size=size)
                )

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

    @staticmethod
    async def _file_size_for_ref(ops: Ops, sub_path: str, file_name: str) -> int:
        """Get the content length for a file (async helper for listPath)."""
        try:
            file_path = sub_path.rstrip("/") + "/" + file_name
            fd = await ops.desc(file_path, validate=False)
            fv = fd.get_latest_version()
            return await ops._client.fc_repo.content_length(fv)
        except Exception:
            return 0

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
            data = bytes(self.buffer)
            self.buffer.clear()

            cfg = get_config().dcfs.download
            max_retries = cfg.upload_max_retries
            base_delay = cfg.upload_base_retry_delay

            last_ex: Optional[Exception] = None
            for attempt in range(max_retries):
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.ops.upload_from_bytes(data, self.path), self.loop
                    )
                    future.result()  # Wait for Discord upload to finish
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
                    time.sleep(delay)

            logger.error(
                f"Upload failed for {self.path} after {max_retries} retries: {last_ex}",
            )
            raise last_ex  # type: ignore[misc]
