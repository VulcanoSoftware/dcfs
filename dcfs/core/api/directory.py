from typing import List, Optional

from dcfs.core.model import DCFSDirectory, DCFSFileRef
from dcfs.errors import DirectoryIsNotEmpty, FileOrDirectoryDoesNotExist

from .file import FileApi
from .message import MessageApi
from .metadata import MetaDataApi


class DirectoryApi:
    def __init__(
        self,
        metadata_api: MetaDataApi,
        file_api: FileApi,
        message_api: MessageApi,
    ):
        self.__metadata_api = metadata_api
        self.__file_api = file_api
        self.__message_api = message_api

    @property
    def root(self):
        return self.__metadata_api.get_root_directory()

    async def create(
        self,
        name: str,
        under: DCFSDirectory,
        dir_to_copy: Optional[DCFSDirectory] = None,
    ) -> DCFSDirectory:
        new_dir = under.create_dir(name, dir_to_copy)
        await self.__metadata_api.push()
        return new_dir

    @staticmethod
    def ls(directory: DCFSDirectory) -> List[DCFSDirectory | DCFSFileRef]:
        return directory.find_dirs() + directory.find_files()

    @staticmethod
    def get_fr(directory: DCFSDirectory, file_name: str) -> DCFSFileRef:
        if f := directory.find_file(file_name):
            return f
        raise FileOrDirectoryDoesNotExist(file_name)

    async def rm_empty(self, directory: DCFSDirectory) -> None:
        if directory.find_dirs() or directory.find_files():
            raise DirectoryIsNotEmpty(directory.absolute_path)
        await self.rm_dangerously(directory)

    async def rm_dangerously(self, directory: DCFSDirectory) -> None:
        message_ids = await self.__collect_subtree_message_ids(directory)
        directory.delete()
        await self.__metadata_api.push()
        await self.__message_api.delete_messages(message_ids)

    async def __collect_subtree_message_ids(
        self, directory: DCFSDirectory
    ) -> List[int]:
        ids: List[int] = []
        for fr in directory.find_files():
            ids.extend(await self.__file_api.collect_message_ids(fr))
        for child in directory.find_dirs():
            ids.extend(await self.__collect_subtree_message_ids(child))
        return ids
