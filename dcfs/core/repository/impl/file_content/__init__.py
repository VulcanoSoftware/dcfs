import asyncio
import logging
from typing import AsyncIterator, Generator, List, Optional

from dcfs.config import get_config
from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSFileVersion
from dcfs.core.repository.interface import IFileContentRepository
from dcfs.errors import TechnicalError, TransientUploadError
from dcfs.reqres import (
    EditMessageMediaReq,
    SentFileMessage,
    UploadableFileMessage,
)
from dcfs.utils.retry import _is_transient

from .file_uploader import FileUploader, discord_max_file_size_bytes


async def _empty_iterator() -> AsyncIterator[bytes]:
    """Return an empty async iterator (no-op)."""
    if False:
        yield b""

logger = logging.getLogger(__name__)


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

            cfg = get_config().dcfs.download
            while retries < cfg.upload_max_retries:
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
                        f"Retry {retries}/{cfg.upload_max_retries} in {cfg.upload_retry_interval}s..."
                    )
                    uploader.reset_buffer()
                    await asyncio.sleep(cfg.upload_retry_interval)

            raise TransientUploadError(
                uploader._file_name, cfg.upload_max_retries,
                last_ex or Exception("Unknown error")
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

        if total_size >= 0:
            # Case 1: Total size is known upfront.
            for i, part_size in enumerate(self._partition(total_size, max_part_size)):
                await self._upload_semaphore.acquire()

                file_msg.name = f"[part{i+1}]{original_name}"
                file_msg.size = part_size

                uploader = FileUploader(self._message_api.discord_api.next_bot, file_msg)
                await uploader.upload()

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
                await asyncio.sleep(0)
                file_msg.next_part(part_size)
        else:
            # Case 2: Total size is unknown (e.g. streaming from SFTP).
            # We read and upload parts until the stream is exhausted.
            i = 0
            while True:
                await self._upload_semaphore.acquire()

                file_msg.name = f"[part{i+1}]{original_name}"
                # Set size to -1 for FileUploader to allow reading up to max_part_size
                # without being capped by FileMessageFromStream.read().
                file_msg.size = -1

                uploader = FileUploader(self._message_api.discord_api.next_bot, file_msg)
                part_size = await uploader.upload()

                if part_size == 0 and i > 0:
                    # EOF reached after some parts were uploaded.
                    self._upload_semaphore.release()
                    break

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
                await asyncio.sleep(0)

                if part_size < max_part_size:
                    # Last part reached.
                    break

                file_msg.next_part(part_size)
                i += 1

        # Wait for all uploads to complete.
        return list(await asyncio.gather(*tasks))

    async def update(self, message_id: int, buffer: bytes, name: str) -> int:
        cfg = get_config().dcfs.download
        retries = 0
        last_ex: Optional[Exception] = None
        while retries < cfg.upload_max_retries:
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
                    f"Transient update failure ({ex}). Retry {retries}/{cfg.upload_max_retries} in {cfg.upload_retry_interval}s..."
                )
                await asyncio.sleep(cfg.upload_retry_interval)

        raise TransientUploadError(name, cfg.upload_max_retries, last_ex or Exception("Unknown error"))

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
        parts = list(self._get_file_part_to_download(fv, begin, end))
        n_parts = len(parts)

        if n_parts == 0:
            return _empty_iterator()

        return self._stream_parts(parts, n_parts)

    async def _stream_parts(
        self,
        parts: list[tuple[int, int, int]],
        n_parts: int,
    ) -> AsyncIterator[bytes]:
        """Stream parts in order via a queue-based producer/consumer pattern.

        Producer tasks download each part from Discord's CDN and push
        ``(part_index, chunk)`` tuples to a shared queue. The consumer
        loop reads from the queue and yields chunks **in part order** so
        that the first byte reaches the WebDAV client as fast as possible
        (≈120 ms instead of waiting for the entire 8 MB first part).

        Out-of-order chunks are buffered and drained once their part
        becomes the current one. On exit or error all producer tasks are
        cancelled.
        """
        logger.info(
            "_stream_parts: starting %d parts, semaphore=%d",
            n_parts,
            self._download_semaphore._value,  # type: ignore[attr-defined]
        )

        queue: asyncio.Queue["tuple[int, Optional[bytes]]"] = asyncio.Queue(
            maxsize=64
        )

        # Shared dict: producer stores its exception HERE before the
        # ``await`` in ``finally`` so the consumer can see it immediately
        # after receiving the sentinel, without waiting for the Task to
        # store the exception (which only happens *after* ``finally``
        # completes).  This avoids a race condition that would otherwise
        # silently swallow the error and leave the consumer waiting
        # forever for data from a failed part → WinSCP timeout.
        _producer_errors: dict[int, Exception] = {}

        async def _producer(
            part_idx: int, message_id: int, part_begin: int, part_end: int
        ) -> None:
            """Download one part, pushing chunks to the shared queue."""
            try:
                async with self._download_semaphore:
                    logger.debug(
                        "_producer %d: acquired semaphore, downloading msg=%d bytes=%d-%d",
                        part_idx, message_id, part_begin, part_end,
                    )
                    resp = await self._message_api.download_file(
                        message_id, part_begin, part_end
                    )
                    chunk_count = 0
                    async for chunk in resp.chunks:
                        await queue.put((part_idx, chunk))
                        chunk_count += 1
                    logger.debug(
                        "_producer %d: finished, %d chunks", part_idx, chunk_count
                    )
            except asyncio.CancelledError:
                logger.debug("_producer %d: cancelled", part_idx)
                raise
            except Exception as ex:
                logger.error("_producer %d: error: %s", part_idx, ex)
                _producer_errors[part_idx] = ex  # store before finally
                raise
            finally:
                await queue.put((part_idx, None))

        producers = [
            asyncio.create_task(_producer(idx, msg_id, part_b, part_e))
            for idx, (msg_id, part_b, part_e) in enumerate(parts)
        ]

        buffers: dict[int, list[bytes]] = {}
        finished: set[int] = set()
        next_idx = 0
        total_yielded = 0
        t_start = asyncio.get_event_loop().time()

        try:
            while next_idx < n_parts:
                # Drain any already-buffered chunks for the next part.
                if next_idx in buffers and buffers[next_idx]:
                    buf_chunk = buffers[next_idx].pop(0)
                    total_yielded += len(buf_chunk)
                    yield buf_chunk
                    continue

                # If the next part is fully finished with no buffered
                # data, advance to the following part.
                if next_idx in finished:
                    logger.debug("_stream_parts: part %d finished, advancing to %d", next_idx, next_idx + 1)
                    next_idx += 1
                    continue

                # Wait for the next chunk from any producer.
                part_idx, chunk = await queue.get()

                if chunk is None:
                    finished.add(part_idx)
                    # Check the shared error dict BEFORE checking
                    # task.exception() to avoid a race condition where
                    # ``finally`` yields to the event loop via await
                    # before the task has stored the exception.
                    if part_idx in _producer_errors:
                        exc = _producer_errors[part_idx]
                        logger.error(
                            "_stream_parts: producer %d failed: %s", part_idx, exc
                        )
                        raise exc
                    # Also check task.exception() as a fallback for
                    # exceptions that bypass the ``except`` clause
                    # (e.g. GeneratorExit from aclose).
                    # task.exception() returns BaseException | None,
                    # but we only care about Exception subclasses.
                    task_exc = producers[part_idx].exception()
                    if task_exc is not None:
                        logger.error(
                            "_stream_parts: producer %d failed (late): %s", part_idx, task_exc
                        )
                        if isinstance(task_exc, Exception):
                            raise task_exc
                else:
                    if part_idx == next_idx:
                        total_yielded += len(chunk)
                        yield chunk
                    else:
                        buffers.setdefault(part_idx, []).append(chunk)

        finally:
            t_end = asyncio.get_event_loop().time()
            logger.info(
                "_stream_parts: done in %.2fs, yielded %d bytes across %d parts",
                t_end - t_start, total_yielded, n_parts,
            )
            for t in producers:
                if not t.done():
                    t.cancel()
