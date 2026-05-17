"""
File uploader for the Discord storage backend.

Discord's upload model is simpler than Telegram's MTProto chunked upload:
 - There is no separate "save file part" step on the server side.
 - Files are uploaded as multipart/form-data attachments in a single POST.
 - The maximum attachment size depends on the server boost level:
     free / unbooted : 25 MB
     level 2 boost   : 50 MB
     level 3 boost   : 100 MB
   We treat max_file_size_mb (from config) as the ceiling per part.

Because the codebase was originally designed around Telegram's two-phase
upload (accumulate parts → send), we keep that interface intact:
 - save_file_part / save_big_file_part store chunks in the DiscordAPI buffer.
 - send_small_file / send_big_file flush the buffer to Discord.
"""

import asyncio
import logging
import random
from dataclasses import dataclass

from dcfs.errors import TechnicalError
from dcfs.reqres import (
    SaveBigFilePartReq,
    SaveFilePartReq,
    SendFileReq,
    SendMessageResp,
    UploadableFileMessage,
    UploadedFile,
)
from dcfs.discord.interface import ITDLibClient

logger = logging.getLogger(__name__)


def get_appropriated_part_size(file_size: int) -> int:
    """Return chunk size in KB for a given file size."""
    if file_size <= 1 * 1024 * 1024:
        return 32
    if file_size <= 10 * 1024 * 1024:
        return 64
    return 512


def generate_random_long() -> int:
    return random.randint(-(2**63), 2**63 - 1)


def is_big_file(size: int) -> bool:
    return size > 10 * 1024 * 1024  # 10 MB


@dataclass
class WorkersConfig:
    small: int = 3
    big: int = 5


@dataclass
class FileChunk:
    content: bytes
    file_part: int


class FileUploader:
    def __init__(
        self,
        client: ITDLibClient,
        file_msg: UploadableFileMessage,
        workers=WorkersConfig(),
    ):
        self.client = client
        self._file_msg = file_msg
        self._file_size = self._file_msg.get_size()
        self._file_name = self._file_msg.file_name()

        self._chunk_size = get_appropriated_part_size(self._file_size) * 1024
        self._total_parts = (self._file_size + self._chunk_size - 1) // self._chunk_size

        self._part_indexes: asyncio.Queue[int] = asyncio.Queue(
            maxsize=self._total_parts
        )

        self._workers = workers
        self._file_id = generate_random_long()
        self._is_big = is_big_file(self._file_size)
        self._read_size = 0
        self._uploaded_size = 0
        self._num_workers = self._workers.big if self._is_big else self._workers.small
        self._lock = asyncio.Lock()

    async def _close(self) -> None:
        await self._file_msg.close()

    async def _read(self, length: int) -> bytes:
        return await self._file_msg.read(length)

    async def _upload_chunk(self, chunk: FileChunk) -> None:
        attempt = 0
        while True:
            try:
                if self._is_big:
                    rsp = await self.client.save_big_file_part(
                        SaveBigFilePartReq(
                            file_id=self._file_id,
                            bytes=chunk.content,
                            file_part=chunk.file_part,
                            file_total_parts=self._total_parts,
                        )
                    )
                else:
                    rsp = await self.client.save_file_part(
                        SaveFilePartReq(
                            file_id=self._file_id,
                            bytes=chunk.content,
                            file_part=chunk.file_part,
                        )
                    )

                if not rsp.success:
                    raise TechnicalError(f"Unexpected response: {rsp}")

                self._uploaded_size += len(chunk.content)
                return

            except Exception as e:
                logger.warning(
                    f"Error uploading part {chunk.file_part} for {self._file_name}: {e}, attempt={attempt + 1}"
                )
                attempt += 1

    def _done_reading(self) -> bool:
        return self._read_size >= self._file_size

    async def _upload_next_part(self, part: int) -> int:
        async with self._lock:
            if self._done_reading():
                return 0
            size_to_read = min(self._file_size - self._read_size, self._chunk_size)
            content = await self._read(size_to_read)
            self._read_size += size_to_read

        await self._upload_chunk(FileChunk(content=content, file_part=part))
        return size_to_read

    async def _cancelled(self) -> bool:
        if tt := self._file_msg.task_tracker:
            return await tt.cancelled()
        return False

    async def upload(self) -> int:
        await self._file_msg.open()

        for i in range(self._total_parts):
            await self._part_indexes.put(i)

        async def create_worker(worker_id: int) -> bool:
            while True:
                if await self._cancelled():
                    logger.warning(
                        f"Task uploading for {self._file_name} was cancelled. Worker {worker_id} exiting."
                    )
                    return False

                try:
                    part_size = await self._upload_next_part(
                        self._part_indexes.get_nowait()
                    )
                except asyncio.QueueEmpty:
                    logger.debug(
                        f"[Worker {worker_id}] No more parts to upload for {self._file_name}. Worker exiting."
                    )
                    return True
                logger.debug(
                    f"[Worker {worker_id}] {self._uploaded_size * 100 / self._file_size:.1f}% uploaded. "
                    f"file_id={self._file_id} file_name={self._file_name}"
                )
                if (tt := self._file_msg.task_tracker) and part_size > 0:
                    await tt.update_progress(size_delta=part_size)

        await asyncio.gather(
            *(create_worker(worker_id) for worker_id in range(self._num_workers))
        )

        await asyncio.sleep(0.5)
        await self._close()
        return self._file_size

    def get_uploaded_file(self) -> UploadedFile:
        return UploadedFile(
            id=self._file_id,
            parts=self._total_parts,
            name=self._file_name,
        )

    async def send(self, chat_id: int, caption: str = "") -> SendMessageResp:
        logger.debug(
            f"Sending file {self._file_name} ({self._file_id}) to channel {chat_id}"
        )

        req = SendFileReq(
            chat=chat_id,
            file=self.get_uploaded_file(),
            name=self._file_name,
            caption=caption,
        )

        if self._is_big:
            return await self.client.send_big_file(req)
        return await self.client.send_small_file(req)
