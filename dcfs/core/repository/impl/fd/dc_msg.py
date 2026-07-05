import asyncio
import json
import logging
from itertools import chain
from typing import Optional

from dcfs.config import get_config
from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSFileDesc, DCFSFileRef
from dcfs.core.model.file import INVALID_FILE_SIZE
from dcfs.core.repository.interface import (
    FDRepositoryResp,
    IFDRepository,
)
from dcfs.errors import MessageNotFound
from dcfs.utils.retry import _is_transient

logger = logging.getLogger(__name__)


class DCMsgFDRepository(IFDRepository):
    def __init__(self, message_api: MessageApi):
        self._message_api = message_api

    async def _send_with_retry(self, text: str) -> int:
        """Send a file descriptor with exponential backoff retry."""
        cfg = get_config().dcfs.download
        max_retries = cfg.upload_max_retries
        base_delay = cfg.upload_base_retry_delay

        last_ex: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                return await self._message_api.send_text(text)
            except Exception as ex:
                last_ex = ex
                if not _is_transient(ex):
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Transient failure sending file descriptor ({ex}). "
                    f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        raise last_ex  # type: ignore[misc]

    async def _edit_with_retry(self, message_id: int, text: str) -> int:
        """Edit a file descriptor with exponential backoff retry.

        Falls back to creating a new descriptor if the original message
        was deleted (MessageNotFound).
        """
        cfg = get_config().dcfs.download
        max_retries = cfg.upload_max_retries
        base_delay = cfg.upload_base_retry_delay

        last_ex: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                return await self._message_api.edit_message_text(
                    message_id=message_id, message=text
                )
            except MessageNotFound:
                # Message was manually deleted — create a fresh one
                return await self._send_with_retry(text)
            except Exception as ex:
                last_ex = ex
                if not _is_transient(ex):
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Transient failure editing file descriptor ({ex}). "
                    f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        raise last_ex  # type: ignore[misc]

    async def save(
        self, fd: DCFSFileDesc, fr: Optional[DCFSFileRef] = None
    ) -> FDRepositoryResp:
        if fr is None:
            return FDRepositoryResp(
                message_id=await self._send_with_retry(fd.to_json()),
                fd=fd,
            )

        return FDRepositoryResp(
            message_id=await self._edit_with_retry(
                message_id=fr.message_id, text=fd.to_json()
            ),
            fd=fd,
        )

    async def _validate_fv(
        self, fd: DCFSFileDesc, include_all_versions: bool
    ) -> DCFSFileDesc:
        versions = fd.get_versions(exclude_invalid=True)

        # Files in the channel may be deleted manually, so we need to check if the messages for the versions exist.

        file_messages = await self._message_api.get_messages(
            list(chain(*(version.message_ids for version in versions)))
        )

        message_map = {msg.message_id: msg for msg in file_messages if msg}

        has_valid_version = False

        for version in versions:
            version.part_sizes.clear()
            for j, message_id in enumerate(version.message_ids):
                if (
                    not (file_message := message_map.get(message_id, None))
                    or not file_message.document
                ):
                    logger.warning(
                        f"File message {message_id} for part {j + 1} of {fd.name}@{version.id} not found"
                    )
                    version.set_invalid()
                    break
                version.part_sizes.append(file_message.document.size)

            # Reset _size so the size property recomputes from part_sizes.
            # This keeps _size consistent with the freshly-rebuilt part_sizes.
            version._size = INVALID_FILE_SIZE

            if version.is_valid():
                has_valid_version = True
                if not include_all_versions:
                    return fd

        return fd if has_valid_version else DCFSFileDesc.empty(fd.name)

    async def get(
        self,
        fr: DCFSFileRef,
        include_all_versions: bool = False,
        validate: bool = True,
    ) -> DCFSFileDesc:
        message = (await self._message_api.get_messages([fr.message_id]))[0]

        if not message:
            logging.error(
                f"File descriptor (message_id: {fr.message_id}) for {fr.name} not found"
            )
            return DCFSFileDesc.empty(fr.name)

        fd = DCFSFileDesc.from_dict(json.loads(message.text), name=fr.name)
        if not validate:
            return fd

        return await self._validate_fv(fd, include_all_versions)
