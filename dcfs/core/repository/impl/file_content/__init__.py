import asyncio
import logging
from typing import AsyncIterator, Generator, List, Optional

from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSFileVersion
from dcfs.core.repository.interface import IFileContentRepository
from dcfs.errors import TechnicalError, TransientUploadError
from dcfs.reqres import (
    EditMessageMediaReq,
    SentFileMessage,
    UploadableFileMessage,
)

from .file_uploader import FileUploader, discord_max_file_size_bytes

logger = logging.getLogger(__name__)
RETRY_INTERVAL = 5  # seconds
MAX_RETRIES = 10


def _is_transient(ex: Exception) -> bool:
    """Classify a Discord upload error as transient (retryable) or permanent."""
    from dcfs.errors import FileSizeTooLarge

    if isinstance(ex, FileSizeTooLarge):
        return False

    if hasattr(ex, "retry_after"):
        return True

    status = getattr(ex, "status", None)
    if status is not None:
        if status == 429:  # Rate Limited
            return True
        if 500 <= status < 600:  # Server errors
            return True
        if 400 <= status < 500:
            return False

    if isinstance(ex, (asyncio.TimeoutError, ConnectionError, IOError)):
        return True

    return False


class DCMsgFileContentRepository(IFileContentRepository):
    def __init__(self, message_api: MessageApi, max_concurrent_parts: int = 3):
        self._message_api = message_api
        self._download_semaphore = asyncio.Semaphore(max_concurrent_parts)
        self._upload_semaphore = asyncio.Semaphore(max_concurrent_parts)

    async def _upload_part_task(
        self,
        uploader: FileUploader,
        chat_id: int,
        part_num: int,
        part_size: int,
        semaphore: asyncio.Semaphore,
    ) -> SentFileMessage:
        """Helper task to send a buffered part to Discord with retries."""
        try:
            retries = 0
            last_ex: Optional[Exception] = None

            while retries < MAX_RETRIES:
                try:
                    resp = await uploader.send(chat_id)
                    return SentFileMessage(message_id=resp.message_id, size=part_size)
                except Exception as ex:
                    last_ex = ex
                    if not _is_transient(ex):
                        logger.error(f"Permanent upload failure for part {part_num}: {ex}")
                        raise TechnicalError(
                            f"Permanent upload failure for part {part_num}: {ex}"
                        ) from ex

                    retries += 1
                    logger.warning(
                        f"Transient upload failure for part {part_num} ({ex}). "
                        f"Retry {retries}/{MAX_RETRIES} in {RETRY_INTERVAL}s..."
                    )
                    uploader.reset_buffer()
                    await asyncio.sleep(RETRY_INTERVAL)

            raise TransientUploadError(
                uploader._file_name, MAX_RETRIES, last_ex or Exception("Unknown error")
            )
        finally:
            semaphore.release()

    @staticmethod
    def _partition(size: int, part_size: int):
        parts = (size + part_size - 1) // part_size
        for i in range(parts - 1):
            yield part_size
        yield size - (parts - 1) * part_size

    async def save(self, file_msg: UploadableFileMessage) -> List[SentFileMessage]:
        total_size = file_msg.get_size()
        original_name = file_msg.name or "unnamed"
        tasks = []

        max_part_size = discord_max_file_size_bytes()
        for i, part_size in enumerate(self._partition(total_size, max_part_size)):
            # Acquire semaphore BEFORE buffering to keep memory usage under control.
            # Only N parts will be buffered and uploading concurrently.
            await self._upload_semaphore.acquire()

            # Update file_msg for the current part
            file_msg.name = f"[part{i+1}]{original_name}"
            file_msg.size = part_size

            # Create an uploader for this part. Using next_bot to distribute load
            # across multiple bots if available.
            uploader = FileUploader(self._message_api.discord_api.next_bot, file_msg)

            # Read and buffer the part content sequentially from the source stream.
            await uploader.upload()

            # Dispatch the upload as a background task.
            tasks.append(
                asyncio.create_task(
                    self._upload_part_task(
                        uploader,
                        self._message_api.private_file_channel,
                        i + 1,
                        part_size,
                        self._upload_semaphore,
                    )
                )
            )

            # Advance the source message to the next part
            file_msg.next_part(part_size)

        # Wait for all uploads to complete.
        return list(await asyncio.gather(*tasks))

    async def update(self, message_id: int, buffer: bytes, name: str) -> int:
        retries = 0
        last_ex: Optional[Exception] = None
        while retries < MAX_RETRIES:
            try:
                resp = await self._message_api.discord_api.bot.edit_message_media(
                    EditMessageMediaReq(
                        chat=self._message_api.private_file_channel,
                        message_id=message_id,
                        buffer=buffer,
                        name=name,
                    )
                )
                return resp.message_id
            except Exception as ex:
                last_ex = ex
                if not _is_transient(ex):
                    logger.error(f"Permanent update failure: {ex}")
                    raise TechnicalError(f"Permanent update failure: {ex}") from ex

                retries += 1
                logger.warning(
                    f"Transient update failure ({ex}). Retry {retries}/{MAX_RETRIES} in {RETRY_INTERVAL}s..."
                )
                await asyncio.sleep(RETRY_INTERVAL)

        raise TransientUploadError(name, MAX_RETRIES, last_ex or Exception("Unknown error"))

    def _get_file_part_to_download(
        self, fv: DCFSFileVersion, begin: int, end: int
    ) -> Generator[tuple[int, int, int], None, None]:
        current_pos = 0
        for msg_id, part_size in zip(fv.message_ids, fv.part_sizes):
            part_end_pos = current_pos + part_size - 1

            if begin <= part_end_pos and (end == -1 or end >= current_pos):
                part_begin = max(0, begin - current_pos)
                if end == -1:
                    part_end = part_size - 1
                else:
                    part_end = min(part_size - 1, end - current_pos)

                yield msg_id, part_begin, part_end

            current_pos += part_size

    async def get(self, fv: DCFSFileVersion, begin: int, end: int, name: str) -> AsyncIterator[bytes]:
        async def _download_one(message_id: int, part_begin: int, part_end: int):
            async with self._download_semaphore:
                return await self._message_api.download_file(
                    message_id, part_begin, part_end
                )

        tasks = [
            asyncio.create_task(_download_one(msg_id, part_b, part_e))
            for msg_id, part_b, part_e in self._get_file_part_to_download(
                fv, begin, end
            )
        ]

        async def _ordered_stream():
            try:
                for task in tasks:
                    result = await task
                    async for chunk in result.chunks:
                        yield chunk
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()

        return _ordered_stream()
