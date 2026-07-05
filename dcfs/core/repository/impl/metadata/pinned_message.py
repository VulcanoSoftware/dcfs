import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from dcfs.config import get_config
from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSDirectory, DCFSFileVersion, DCFSMetadata
from dcfs.core.repository.interface import IFileContentRepository, IMetaDataRepository
from dcfs.errors import (
    MetadataNotInitialized,
    NoPinnedMessage,
)
from dcfs.reqres import (
    FileMessageFromBuffer,
    MessageResp,
    SentFileMessage,
)
from dcfs.utils.retry import _is_transient

logger = logging.getLogger(__name__)


class DCMsgMetadataRepository(IMetaDataRepository):
    METADATA_FILE_NAME = "metadata.json"

    def __init__(self, message_api: MessageApi, fc_repo: IFileContentRepository):
        super().__init__()

        self._message_api = message_api
        self._fc_repo = fc_repo

        self._message_id: Optional[int] = None

    async def push(self) -> None:
        if not self.metadata:
            raise MetadataNotInitialized()

        buffer = json.dumps(self.metadata.to_dict()).encode()
        if self._message_id is not None:
            await self._fc_repo.update(
                self._message_id,
                buffer,
                self.METADATA_FILE_NAME,
            )
        else:
            resp = await self._fc_repo.save(
                FileMessageFromBuffer.new(
                    name=self.METADATA_FILE_NAME,
                    buffer=buffer,
                )
            )
            message_id = resp[0].message_id

            cfg = get_config().dcfs.download
            max_retries = cfg.upload_max_retries
            base_delay = cfg.upload_base_retry_delay
            last_ex: Optional[Exception] = None

            for attempt in range(max_retries):
                try:
                    await self._message_api.pin_message(message_id=message_id)
                    last_ex = None
                    break
                except Exception as ex:
                    last_ex = ex
                    if not _is_transient(ex):
                        logger.error(
                            f"Non-transient error pinning metadata message {message_id}: {ex}"
                        )
                        raise
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Transient error pinning metadata message {message_id} "
                        f"(attempt {attempt + 1}/{max_retries}): {ex}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            if last_ex is not None:
                logger.error(
                    f"Failed to pin metadata message {message_id} after "
                    f"{max_retries} retries: {last_ex}"
                )
                raise last_ex  # type: ignore[misc]

            self._message_id = message_id

    async def _get_pinned_with_retry(self) -> list[MessageResp]:
        cfg = get_config().dcfs.download
        max_retries = cfg.upload_max_retries
        base_delay = cfg.upload_base_retry_delay
        last_ex: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                return await self._message_api.get_pinned_messages()
            except Exception as ex:
                last_ex = ex
                if not _is_transient(ex):
                    logger.error(
                        f"Non-transient error getting pinned messages: {ex}"
                    )
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Transient error getting pinned messages "
                    f"(attempt {attempt + 1}/{max_retries}): {ex}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        logger.error(
            f"Failed to get pinned messages after {max_retries} retries: {last_ex}"
        )
        raise last_ex  # type: ignore[misc]

    @staticmethod
    async def _read_all(async_iter: AsyncIterator[bytes]) -> bytes:
        result = bytearray()
        async for chunk in async_iter:
            result.extend(chunk)
        return bytes(result)

    async def new_metadata(self) -> MessageResp:
        root = DCFSDirectory.root_dir()
        self.metadata = DCFSMetadata(root)
        self._message_id = None
        await self.push()
        pinned_messages = await self._get_pinned_with_retry()
        if not pinned_messages:
            raise NoPinnedMessage()
        return pinned_messages[0]

    async def get(self) -> DCFSMetadata:
        try:
            pinned_messages = await self._get_pinned_with_retry()
            if not pinned_messages:
                raise NoPinnedMessage()
            pinned_message = pinned_messages[0]
        except NoPinnedMessage:
            pinned_message = await self.new_metadata()

        if pinned_message.document is None:
            raise NoPinnedMessage()
        temp_fv = DCFSFileVersion.from_sent_file_message(
            SentFileMessage(pinned_message.message_id, pinned_message.document.size)
        )

        metadata = DCFSMetadata.from_dict(
            json.loads(
                await self._read_all(
                    await self._fc_repo.get(
                        temp_fv,
                        begin=0,
                        end=-1,
                        name=self.METADATA_FILE_NAME,
                    )
                )
            )
        )

        self._message_id = pinned_message.message_id
        self.metadata = metadata
        return metadata
