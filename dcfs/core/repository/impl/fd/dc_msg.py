import json
import logging
from itertools import chain
from typing import Optional

from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSFileDesc, DCFSFileRef
from dcfs.core.repository.interface import (
    FDRepositoryResp,
    IFDRepository,
)
from dcfs.errors import MessageNotFound

logger = logging.getLogger(__name__)


class DCMsgFDRepository(IFDRepository):
    def __init__(self, message_api: MessageApi):
        self._message_api = message_api

    async def save(
        self, fd: DCFSFileDesc, fr: Optional[DCFSFileRef] = None
    ) -> FDRepositoryResp:
        # If file_content referer is None, create a new file_content descriptor message.
        if fr is None:
            return FDRepositoryResp(
                message_id=await self._message_api.send_text(fd.to_json()),
                fd=fd,
            )

        # If file_content referer is provided, try to update the existing file_content descriptor.
        # But if the message is not found (probably got deleted manually), a new file_content descriptor will be created.
        try:
            return FDRepositoryResp(
                message_id=await self._message_api.edit_message_text(
                    message_id=fr.message_id, message=fd.to_json()
                ),
                fd=fd,
            )
        except MessageNotFound:
            return await self.save(fd)

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

        for i, version in enumerate(versions):
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
            if version.is_valid():
                has_valid_version = True
                if not include_all_versions:
                    # Found a valid version, no need to check further
                    return fd

        return fd if has_valid_version else DCFSFileDesc.empty(fd.name)

    async def get(
        self, fr: DCFSFileRef, include_all_versions: bool = False
    ) -> DCFSFileDesc:
        message = (await self._message_api.get_messages([fr.message_id]))[0]

        if not message:
            logging.error(
                f"File descriptor (message_id: {fr.message_id}) for {fr.name} not found"
            )
            return DCFSFileDesc.empty(fr.name)

        fd = DCFSFileDesc.from_dict(json.loads(message.text), name=fr.name)
        return await self._validate_fv(fd, include_all_versions)
