import datetime
import json
from dataclasses import dataclass, field
from typing import Iterable, List
from uuid import uuid4 as uuid

from dcfs.reqres import SentFileMessage
from dcfs.utils.time import FIRST_DAY_OF_EPOCH, ts

from .common import validate_name
from .serialized import DCFSFileDescSerialized, DCFSFileVersionSerialized

EMPTY_FILE_MESSAGE = -1
INVALID_FILE_SIZE = -1
INVALID_VERSION_ID = ""


@dataclass
class DCFSFileVersion:
    id: str
    updated_at: datetime.datetime
    _size: int = INVALID_FILE_SIZE  # total size

    # file can be split into multiple "file messages", each max 1GB
    message_ids: List[int] = field(default_factory=list)
    part_sizes: List[int] = field(default_factory=list)  # sizes of each part

    @property
    def updated_at_timestamp(self) -> int:
        return ts(self.updated_at)

    @property
    def size(self) -> int:
        if self._size == INVALID_FILE_SIZE and self.part_sizes:
            self._size = sum(self.part_sizes)
        return self._size

    def to_dict(self) -> dict:
        return dict(
            type="FV",
            id=self.id,
            updatedAt=self.updated_at_timestamp,
            messageIds=self.message_ids,
            size=self.size,
        )

    @staticmethod
    def empty() -> "DCFSFileVersion":
        return DCFSFileVersion(
            id=str(uuid()),
            updated_at=datetime.datetime.now(),
            message_ids=[],
        )

    @staticmethod
    def from_sent_file_message(*messages: SentFileMessage) -> "DCFSFileVersion":
        return DCFSFileVersion(
            id=str(uuid()),
            updated_at=datetime.datetime.now(),
            message_ids=[msg.message_id for msg in messages],
            part_sizes=[msg.size for msg in messages],
        )

    @staticmethod
    def from_dict(data: DCFSFileVersionSerialized) -> "DCFSFileVersion":
        if (updated_at_ts := data.get("updatedAt", 0)) > 0:
            updated_at = datetime.datetime.fromtimestamp(updated_at_ts / 1000)
        else:
            updated_at = FIRST_DAY_OF_EPOCH

        if (message_ids := data.get("messageIds")) is None:
            if (message_id := data["messageId"]) != EMPTY_FILE_MESSAGE:
                message_ids = [message_id]
            else:
                message_ids = []
        return DCFSFileVersion(
            id=data["id"],
            updated_at=updated_at,
            message_ids=message_ids,
            part_sizes=[],  # part sizes are not serialized
        )

    def set_invalid(self):
        self.message_ids = []
        self.part_sizes = []
        self._size = INVALID_FILE_SIZE

    def is_valid(self) -> bool:
        return bool(self.message_ids)


@dataclass
class DCFSFileDesc:
    name: str
    latest_version_id: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    versions: dict[str, DCFSFileVersion] = field(default_factory=dict)

    @property
    def updated_at_timestamp(self) -> int:
        if not self.versions or self.latest_version_id == INVALID_VERSION_ID:
            return ts(self.created_at)
        return self.get_latest_version().updated_at_timestamp

    def __post_init__(self):
        validate_name(self.name)

    def to_dict(self) -> dict:
        return dict(
            type="F",
            versions=[v.to_dict() for v in self.get_versions(sort=True)],
        )

    @staticmethod
    def from_dict(data: DCFSFileDescSerialized, name: str) -> "DCFSFileDesc":
        versions = {v["id"]: DCFSFileVersion.from_dict(v) for v in data["versions"]}
        if versions:
            latest_version_id = max(
                versions, key=lambda k: versions[k].updated_at_timestamp
            )
        else:
            latest_version_id = INVALID_VERSION_ID
        return DCFSFileDesc(
            name=name,
            latest_version_id=latest_version_id,
            versions=versions,
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @staticmethod
    def empty(name: str) -> "DCFSFileDesc":
        return DCFSFileDesc(
            name=name,
            latest_version_id="",
            versions={},
        )

    def get_latest_version(self) -> DCFSFileVersion:
        return (
            self.versions[self.latest_version_id]
            if self.latest_version_id
            else DCFSFileVersion.empty()
        )

    def get_version(self, version_id: str) -> DCFSFileVersion:
        return self.versions[version_id]

    def add_version(self, version: DCFSFileVersion) -> None:
        self.versions[version.id] = version
        if (
            self.latest_version_id == INVALID_VERSION_ID
            or version.updated_at > self.versions[self.latest_version_id].updated_at
        ):
            self.latest_version_id = version.id
        if not self.created_at or version.updated_at < self.created_at:
            self.created_at = version.updated_at

    def add_empty_version(self) -> None:
        version = DCFSFileVersion.empty()
        self.add_version(version)

    def add_version_from_sent_file_message(self, *msg: SentFileMessage):
        version = DCFSFileVersion.from_sent_file_message(*msg)
        self.add_version(version)
        return self.versions[self.latest_version_id]

    def update_version(self, version_id: str, version: DCFSFileVersion):
        self.versions[version_id] = version

    def get_versions(
        self, sort: bool = False, exclude_invalid: bool = False
    ) -> List[DCFSFileVersion]:
        if not sort:
            res: Iterable[DCFSFileVersion] = self.versions.values()
        else:
            res = sorted(
                self.versions.values(),
                key=lambda v: v.updated_at_timestamp,
                reverse=True,
            )

        if exclude_invalid:
            res = [v for v in res if v.is_valid()]
        return list(res)

    def delete_version(self, version_id: str) -> None:
        if version_id not in self.versions:
            raise ValueError(f"Version {version_id} not found in file {self.name}.")
        del self.versions[version_id]
        if version_id == self.latest_version_id:
            if self.versions:
                self.latest_version_id = max(
                    self.versions, key=lambda k: self.versions[k].updated_at
                )
            else:
                self.latest_version_id = ""
