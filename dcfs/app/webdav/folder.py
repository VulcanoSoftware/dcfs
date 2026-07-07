from typing import Mapping, Tuple

from asgidav.folder import Folder as _Folder
from asgidav.member import Member
from dcfs.app.fs_cache import FSCache, gfc
from dcfs.core import Client, Ops
from dcfs.utils.time import FIRST_DAY_OF_EPOCH, ts

from .resource import Resource


class Folder(_Folder):
    def __init__(self, path: str, client: Client):
        super().__init__(f"/{client.name}{path}")

        self.__relative_path = path
        self.__client = client
        self.__ops = Ops(client)
        self.__folder = client.dir_api.root if path == "/" else self.__ops.cd(path)
        self.__sub_folders = {d.name: d for d in self.__folder.find_dirs()}
        self.__sub_files = {f.name: f for f in self.__folder.find_files()}

    @property
    def fs_cache(self) -> FSCache:
        return gfc[self.__client.name]

    async def display_name(self) -> str:
        return self.__folder.name

    async def member_names(self):
        return set(self.__sub_folders.keys()).union(self.__sub_files.keys())

    async def member(self, path: str):
        path_parts = path.split("/", 1)
        if path_parts[0] == "":
            return self

        name = path_parts[0]
        relative_sub_path = self._sub_path(name)

        if fr := self.__sub_files.get(name):
            if not (res := self.fs_cache.get(relative_sub_path)):
                res = Resource(relative_sub_path, self.__client, fr=fr)
                self.fs_cache.set(relative_sub_path, res)
            return res

        if name in self.__sub_folders:
            if not (sub_folder := self.fs_cache.get(relative_sub_path)):
                sub_folder = Folder(f"{relative_sub_path}/", self.__client)
                self.fs_cache.set(relative_sub_path, sub_folder)

            if len(path_parts) > 1:
                return await sub_folder.member(path_parts[1])
            return sub_folder

        return None

    def _sub_path(self, name: str):
        return f"{self.__relative_path}{name}"

    async def create_empty_resource(self, path: str):
        self.fs_cache.reset(self.__relative_path)
        names = path.split("/", 1)

        if len(names) > 1:
            sub_folder = await self.member(names[0])
            if not isinstance(sub_folder, Folder):
                raise ValueError(f"{self._sub_path(names[0])} is not a folder")
            return await sub_folder.create_empty_resource(names[1])

        if names[0] == "":
            raise ValueError("the requested path is a folder")

        if names[0] not in self.__sub_files:
            await self.__ops.touch(self._sub_path(names[0]))

        return Resource(self._sub_path(names[0]), self.__client)

    async def create_folder(self, name: str):
        self.fs_cache.reset(self.__relative_path)
        return await self.__ops.mkdir(self._sub_path(name), False)

    async def creation_date(self) -> int:
        return self.__folder.created_at_timestamp

    async def last_modified(self) -> int:
        return self.__folder.modified_at_timestamp

    async def remove(self) -> None:
        self.fs_cache.reset_parent(self.__relative_path)
        await self.__ops.rm_dir(self.__relative_path.rstrip("/"), True)

    async def copy_to(self, destination: str) -> None:
        self.fs_cache.reset_parent(destination)
        await self.__ops.cp_dir(
            self.__relative_path.rstrip("/"), destination.rstrip("/")
        )

    async def move_to(self, destination: str) -> None:
        self.fs_cache.reset_parent(self.__relative_path)
        self.fs_cache.reset_parent(destination)
        await self.__ops.mv_dir(
            self.__relative_path.rstrip("/"), destination.rstrip("/")
        )


class RootFolder(_Folder):
    def __init__(self, sub_folders: Mapping[str, Folder]):
        super().__init__("/")

        self._members = sub_folders
        self._member_names = frozenset(sub_folders.keys())

    def _route(self, path: str) -> Tuple[Folder, str]:
        """
        "a/b/c" -> (self._members["a"], "b/c")
        """
        parts = path.split("/", 1)
        if len(parts) == 1:
            return self._members[parts[0]], ""
        return self._members[parts[0]], parts[1]

    async def display_name(self) -> str:
        return "root"

    async def member_names(self) -> Tuple[str, ...]:
        return tuple(self._member_names)

    async def member(self, path: str):
        if path == "":
            return self
        folder, sub_path = self._route(path)
        return await folder.member(sub_path)

    async def create_empty_resource(self, path: str) -> Member:
        folder, sub_path = self._route(path)
        return await folder.create_empty_resource(sub_path)

    async def creation_date(self) -> int:
        return ts(FIRST_DAY_OF_EPOCH)

    async def last_modified(self) -> int:
        return ts(FIRST_DAY_OF_EPOCH)

    async def remove(self) -> None:
        raise NotImplementedError("RootFolder does not support removal")

    async def copy_to(self, destination: str) -> None:
        raise NotImplementedError("RootFolder does not support copying")

    async def move_to(self, destination: str) -> None:
        raise NotImplementedError("RootFolder does not support moving")
