from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from dcfs.core.model import (
    DCFSDirectory,
    DCFSFileDesc,
    DCFSFileRef,
    DCFSFileVersion,
    DCFSMetadata,
)
from dcfs.errors import MetadataNotInitialized
from dcfs.reqres import FileContent, SentFileMessage, UploadableFileMessage


@dataclass
class FDRepositoryResp:
    message_id: int
    fd: DCFSFileDesc


class IFileContentRepository(metaclass=ABCMeta):
    @abstractmethod
    async def save(self, file_msg: UploadableFileMessage) -> List[SentFileMessage]:
        pass

    @abstractmethod
    async def get(
        self,
        fv: DCFSFileVersion,
        begin: int,
        end: int,
        name: str,
    ) -> FileContent:
        pass

    @abstractmethod
    async def update(self, message_id: int, buffer: bytes, name: str) -> int:
        pass

    async def content_length(self, fv: DCFSFileVersion) -> int:
        """Logical size of the file as seen by the caller.

        Defaults to the stored on-wire size. The encryption decorator overrides
        this to subtract its per-chunk overhead and the file header so WebDAV
        clients see the plaintext length.
        """
        return fv.size


class IFDRepository(metaclass=ABCMeta):
    @abstractmethod
    async def save(
        self, fd: DCFSFileDesc, fr: Optional[DCFSFileRef] = None
    ) -> FDRepositoryResp:
        pass

    @abstractmethod
    async def get(
        self, fr: DCFSFileRef, validate: bool = True
    ) -> DCFSFileDesc:
        pass


class IMetaDataRepository(metaclass=ABCMeta):
    def __init__(self):
        self.metadata: Optional[DCFSMetadata] = None

    async def init(self):
        self.metadata = await self.get()

    @abstractmethod
    async def push(self) -> None:
        pass

    @abstractmethod
    async def get(self) -> DCFSMetadata:
        pass

    def root(self) -> DCFSDirectory:
        if not self.metadata:
            raise MetadataNotInitialized
        return self.metadata.dir
