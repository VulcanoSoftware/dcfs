from dcfs.core.model import DCFSDirectory, DCFSMetadata
from dcfs.core.repository.interface import IMetaDataRepository


class MetaDataApi:
    def __init__(self, metadata_repo: IMetaDataRepository):
        self.__metadata_repo = metadata_repo

    async def init(self) -> None:
        await self.__metadata_repo.init()

    def reset(self) -> None:
        self.__metadata_repo.metadata = DCFSMetadata(dir=DCFSDirectory.root_dir())

    async def push(self) -> None:
        await self.__metadata_repo.push()

    def get_root_directory(self) -> DCFSDirectory:
        return self.__metadata_repo.root()
