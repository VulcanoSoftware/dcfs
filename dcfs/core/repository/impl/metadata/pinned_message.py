import json
from typing import AsyncIterator, Optional

from dcfs.core.api import MessageApi
from dcfs.core.model import DCFSDirectory, DCFSFileVersion, DCFSMetadata
from dcfs.core.repository.interface import IFileContentRepository, IMetaDataRepository
from dcfs.errors import (
    MetadataNotInitialized,
    NoPinnedMessage,
)
from dcfs.reqres import (
    FileMessageFromBuffer,
    MessageRespWithDocument,
    SentFileMessage,
)


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
            await self._message_api.pin_message(message_id=message_id)
            self._message_id = message_id

    @staticmethod
    async def _read_all(async_iter: AsyncIterator[bytes]) -> bytes:
        result = bytearray()
        async for chunk in async_iter:
            result.extend(chunk)
        return bytes(result)

    async def new_metadata(self) -> MessageRespWithDocument:
        root = DCFSDirectory.root_dir()
        self.metadata = DCFSMetadata(root)
        self._message_id = None
        await self.push()
        pinned_messages = await self._message_api.get_pinned_messages()
        if not pinned_messages:
            raise NoPinnedMessage()
        return pinned_messages[0]  # type: ignore

    async def get(self) -> DCFSMetadata:
        try:
            pinned_messages = await self._message_api.get_pinned_messages()
            if not pinned_messages:
                raise NoPinnedMessage()
            pinned_message = pinned_messages[0]
        except NoPinnedMessage:
            pinned_message = await self.new_metadata()

        assert pinned_message.document is not None
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
