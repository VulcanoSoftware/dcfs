from typing import List, Optional

from dcfs.core.model import DCFSFileDesc, DCFSFileRef, DCFSFileVersion
from dcfs.core.repository.interface import (
    FDRepositoryResp,
    IFDRepository,
    IFileContentRepository,
)
from dcfs.reqres import (
    FileContent,
    FileMessage,
    FileMessageImported,
    SentFileMessage,
    UploadableFileMessage,
)


class FileDescApi:
    def __init__(self, fd_repo: IFDRepository, fc_repo: IFileContentRepository):
        self.__fd_repo = fd_repo
        self.__fc_repo = fc_repo

    async def create_file_desc(self, file_msg: FileMessage) -> FDRepositoryResp:
        return await self.append_file_version(file_msg, fr=None)

    async def get_file_desc(self, fr: DCFSFileRef) -> DCFSFileDesc:
        return await self.__fd_repo.get(fr)

    async def download_file_at_version(
        self, fv: DCFSFileVersion, begin: int, end: int, as_name: str
    ) -> FileContent:
        return await self.__fc_repo.get(
            fv=fv,
            begin=begin,
            end=end,
            name=as_name,
        )

    async def get_sent_file_message(
        self, file_msg: UploadableFileMessage | FileMessageImported
    ) -> List[SentFileMessage]:
        if isinstance(file_msg, FileMessageImported):
            return [SentFileMessage(file_msg.message_id, file_msg.size)]
        return await self.__fc_repo.save(file_msg)

    async def append_file_version(
        self, file_msg: FileMessage, fr: Optional[DCFSFileRef] = None
    ) -> FDRepositoryResp:
        fd = await self.get_file_desc(fr) if fr else DCFSFileDesc(name=file_msg.name)

        if isinstance(file_msg, UploadableFileMessage | FileMessageImported):
            sent_file_msg = await self.get_sent_file_message(file_msg)
            fd.add_version_from_sent_file_message(*sent_file_msg)
        else:
            fd.add_empty_version()

        return await self.__fd_repo.save(fd, fr)

    async def update_file_version(
        self, fr: DCFSFileRef, file_msg: FileMessage, version_id: str
    ) -> FDRepositoryResp:
        fd = await self.get_file_desc(fr)
        if isinstance(file_msg, UploadableFileMessage | FileMessageImported):
            sent_file_msg = await self.get_sent_file_message(file_msg)
            fv = DCFSFileVersion.from_sent_file_message(*sent_file_msg)
            fv.id = version_id
            fd.update_version(version_id, fv)
        else:
            fv = fd.get_version(version_id)
            fv.set_invalid()
            fd.update_version(version_id, fv)

        return await self.__fd_repo.save(fd, fr)

    async def delete_file_version(
        self, fr: DCFSFileRef, version_id: str
    ) -> FDRepositoryResp:
        fd = await self.get_file_desc(fr)
        fd.delete_version(version_id)
        return await self.__fd_repo.save(fd, fr)
