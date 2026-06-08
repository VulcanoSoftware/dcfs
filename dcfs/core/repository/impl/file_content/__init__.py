import asyncio
import logging
from typing import Generator, List, AsyncIterator

from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSFileVersion
from dcfs.core.repository.interface import IFileContentRepository
from dcfs.errors import TechnicalError, TransientUploadError
from dcfs.reqres import (
    EditMessageMediaReq,
    FileContent,
    FileMessageFromBuffer,
    SentFileMessage,
    UploadableFileMessage,
)

from .file_uploader import FileUploader

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


class DCMessageFileContentRepository(IFileContentRepository):
    def __init__(self, message_api: MessageApi, max_concurrent_parts: int = 3):
        self._message_api = message_api
        self._download_semaphore = asyncio.Semaphore(max_concurrent_parts)

    async def save(self, f: FileMessageFromBuffer) -> List[SentFileMessage]:
        uploader = FileUploader(self._message_api)
        for chunk in f.chunks:
            uploader.add_file(UploadableFileMessage(name=f.name, buffer=chunk))

        retries = 0
        while retries < MAX_RETRIES:
            try:
                return await uploader.upload()
            except Exception as ex:
                if not _is_transient(ex):
                    logger.error(f"Permanent upload failure: {ex}")
                    raise TechnicalError(f"Permanent upload failure: {ex}") from ex

                retries += 1
                logger.warning(
                    f"Transient upload failure ({ex}). Retry {retries}/{MAX_RETRIES} in {RETRY_INTERVAL}s..."
                )
                await asyncio.sleep(RETRY_INTERVAL)

        raise TransientUploadError(f"Failed to upload file after {MAX_RETRIES} retries due to transient errors.")

    async def update(self, message_id: int, buffer: bytes, name: str) -> SentFileMessage:
        retries = 0
        while retries < MAX_RETRIES:
            try:
                resp = await self._message_api.edit_message_media(
                    EditMessageMediaReq(
                        message_id=message_id,
                        buffer=buffer,
                        name=name,
                    )
                )
                return SentFileMessage(message_id=resp.message_id, size=len(buffer))
            except Exception as ex:
                if not _is_transient(ex):
                    logger.error(f"Permanent update failure: {ex}")
                    raise TechnicalError(f"Permanent update failure: {ex}") from ex

                retries += 1
                logger.warning(
                    f"Transient update failure ({ex}). Retry {retries}/{MAX_RETRIES} in {RETRY_INTERVAL}s..."
                )
                await asyncio.sleep(RETRY_INTERVAL)

        raise TransientUploadError(f"Failed to update file after {MAX_RETRIES} retries due to transient errors.")

    def _get_file_part_to_download(
        self, fv: DCFSFileVersion, begin: int, end: int
    ) -> Generator[tuple[int, int, int], None, None]:
        current_pos = 0
        for part in fv.parts:
            part_end_pos = current_pos + part.size - 1

            if begin <= part_end_pos and (end == -1 or end >= current_pos):
                part_begin = max(0, begin - current_pos)
                if end == -1:
                    part_end = part.size - 1
                else:
                    part_end = min(part.size - 1, end - current_pos)

                yield part.message_id, part_begin, part_end

            current_pos += part.size

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
