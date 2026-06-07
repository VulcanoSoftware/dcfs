from typing import List, Literal, TypedDict


class DCFSFileVersionSerialized(TypedDict, total=False):
    type: Literal["FV"]
    id: str
    updatedAt: int
    messageId: int
    messageIds: List[int]
    size: int
    partSizes: List[int]


class DCFSFileDescSerialized(TypedDict, total=False):
    type: Literal["F"]
    name: str
    versions: List[DCFSFileVersionSerialized]


class DCFSFileRefSerialized(TypedDict, total=False):
    type: Literal["FR"]
    messageId: int
    name: str


class DCFSDirectorySerialized(TypedDict, total=False):
    type: Literal["D"]
    name: str
    createdAt: int
    modifiedAt: int
    children: List["DCFSDirectorySerialized"]
    files: List[DCFSFileRefSerialized]
