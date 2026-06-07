import asyncio
import logging
from typing import Generator, List

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
    """Classify a Discord upload error as transient (retryable) or permanent.

    Transient errors are things like rate limits (429) and server errors (5xx)
    where retrying after a delay may succeed.  Permanent errors like 413
    (Payload Too Large) will never succeed by retrying.
    """
    from dcfs.errors import FileSizeTooLarge

    if isinstance(ex, FileSizeTooLarge):
        return False

    # discord.py's RateLimited exception has a .retry_after attribute
    if hasattr(ex, "retry_after"):
        return True

    # discord.py HTTPException exposes a .status attribute
    status = getattr(ex, "status", None)
    if status is not None:
        if status == 429:  # Rate Limited
            return True
        if 500 <= status < 600:  # Server errors
            return True
        if 400 <= status < 500:  # Other client errors (incl. 413)
            return False

    # Network / transport errors
    if isinstance(ex, (ConnectionError, TimeoutError, OSError)):
        return True

    # Unknown errors — don't retry blindly
    return False

# Discord's file-size limit covers the entire HTTP multipart request body,
# not just the raw file payload.  Multipart encoding overhead (boundary
# markers, Content-Disposition headers, caption, etc.) adds several KB.
# For unboosted servers the limit is 8 MB; with server boosts it can be
# 25-50 MB.  We use 7 MB as a safe default that works everywhere.
PART_SIZE = 7 * 1024 * 1024


class DCMsgFileContentRepository(IFileContentRepository):
    def __init__(self, message_api: MessageApi, max_concurrent_parts: int = 3):
        if max_concurrent_parts < 1:
            raise ValueError("max_concurrent_parts must be >= 1")
        self._message_api = message_api
        self._download_semaphore = asyncio.Semaphore(max_concurrent_parts)

    async def _send_file(
        self, file_msg: UploadableFileMessage
    ) -> SentFileMessage:
        api = self._message_api.discord_api.next_bot

        uploader = FileUploader(api, file_msg)
        logger.info(
            f"Uploading file {file_msg.name} of size {file_msg.size} bytes to channel {self._message_api.private_file_channel} "
            f"using {(await api.get_me()).name}."
        )
        size = await uploader.upload()

        for attempt in range(MAX_RETRIES + 1):
            try:
                message = await uploader.send(
                    self._message_api.private_file_channel,
                )
                return SentFileMessage(message_id=message.message_id, size=size)
            except Exception as ex:
                if not _is_transient(ex):
                    logger.error(
                        f"Permanent error sending file {file_msg.name}: {ex}"
                    )
                    raise
                if attempt >= MAX_RETRIES:
                    logger.error(
                        f"Failed to send file {file_msg.name} after "
                        f"{MAX_RETRIES} retries: {ex}"
                    )
                    raise TransientUploadError(
                        file_msg.name, MAX_RETRIES, ex
                    ) from ex
                logger.warning(
                    f"Transient error sending file {file_msg.name} "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {ex}. "
                    f"Retrying in {RETRY_INTERVAL}s."
                )
                uploader.reset_buffer()
                await asyncio.sleep(RETRY_INTERVAL)

    @staticmethod
    def _partition(size: int, part_size) -> Generator[int]:
        parts = (size + part_size - 1) // part_size
        for i in range(parts - 1):
            yield part_size
        yield size - (parts - 1) * part_size

    async def save(self, file_msg: UploadableFileMessage) -> List[SentFileMessage]:
        size = file_msg.get_size()

        res: List[SentFileMessage] = []
        file_name = file_msg.name or "unnamed"

        for i, part_size in enumerate(
            self._partition(size, PART_SIZE)
        ):
            file_msg.name = f"[part{i+1}]{file_name}"
            file_msg.size = part_size
            logger.info(
                f"Uploading part {i+1} of {file_name}: "
                f"declared size={part_size} bytes"
            )
            res.append(
                await self._send_file(file_msg)
            )
            file_msg.next_part(part_size)
        return res

    async def update(self, message_id: int, buffer: bytes, name: str) -> int:
        file_msg: FileMessageFromBuffer = FileMessageFromBuffer.new(
            buffer=buffer,
            name=name,
        )

        uploader = FileUploader(self._message_api.discord_api.next_bot, file_msg)
        await uploader.upload()

        for attempt in range(MAX_RETRIES + 1):
            try:
                message = await uploader.client.edit_message_media(
                    EditMessageMediaReq(
                        chat=self._message_api.private_file_channel,
                        message_id=message_id,
                        file=uploader.get_uploaded_file(),
                    )
                )
                return message.message_id
            except Exception as ex:
                if not _is_transient(ex):
                    logger.error(
                        f"Permanent error editing message {message_id}: {ex}"
                    )
                    raise
                if attempt >= MAX_RETRIES:
                    logger.error(
                        f"Failed to edit message {message_id} after "
                        f"{MAX_RETRIES} retries: {ex}"
                    )
                    raise TransientUploadError(
                        name, MAX_RETRIES, ex
                    ) from ex
                logger.warning(
                    f"Transient error editing message {message_id} "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {ex}. "
                    f"Retrying in {RETRY_INTERVAL}s."
                )
                await asyncio.sleep(RETRY_INTERVAL)

    @staticmethod
    def _get_file_part_to_download(
        fv: DCFSFileVersion, begin: int, end: int
    ) -> Generator[tuple[int, int, int]]:
        if fv.size <= 0:
            return
        if end < 0:
            end = fv.size
        if begin < 0:
            raise TechnicalError(
                f"Invalid begin value {begin} for file version {fv.id} with size {fv.size}"
            )
        if begin > end:
            raise TechnicalError(
                f"Invalid range: begin {begin} is greater than end {end} for file version {fv.id}"
            )
        if end > fv.size:
            raise TechnicalError(
                f"Invalid end value {end} for file version {fv.id} with size {fv.size}"
            )

        offset = 0
        i_part = 0

        while i_part < len(fv.part_sizes) and offset + fv.part_sizes[i_part] <= begin:
            offset += fv.part_sizes[i_part]
            i_part += 1

        if i_part >= len(fv.part_sizes):
            raise TechnicalError(
                f"Begin offset {begin} exceeds total file size {fv.size} for file version {fv.id}"
            )

        while i_part < len(fv.part_sizes) and offset < end:
            part_size = fv.part_sizes[i_part]
            part_begin = max(0, begin - offset)
            part_end = min(part_size, end - offset)
            if part_begin < part_end:
                yield fv.message_ids[i_part], part_begin, part_end
            offset += part_size
            i_part += 1

    async def get(
        self, fv: DCFSFileVersion, begin: int, end: int, name: str
    ) -> FileContent:
        logger.info(f"Retrieving file content for {name}@{fv.id} from {begin} to {end}")

        async def _download_one(message_id: int, part_begin: int, part_end: int):
            async with self._download_semaphore:
                return await self._message_api.download_file(
                    message_id, part_begin, part_end
                )

        # Build asyncio.Tasks so all downloads start in the background
        # immediately (concurrency gated by self._download_semaphore).
        # The list comprehension eagerly consumes the generator so all
        # tasks are spawned before we start awaiting any of them.
        tasks = [
            asyncio.create_task(_download_one(msg_id, part_b, part_e))
            for msg_id, part_b, part_e in self._get_file_part_to_download(
                fv, begin, end
            )
        ]

        async def _ordered_stream():
            """Yield bytes from each part in order as soon as it is ready.

            Tasks run in the background (up to MAX_CONCURRENT_PARTS at a time)
            so later parts may already be downloaded by the time we finish
            streaming earlier ones -- eliminating the gather-all-then-start
            bottleneck.
            """
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
