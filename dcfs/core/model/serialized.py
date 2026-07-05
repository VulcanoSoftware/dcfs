from typing import List, Literal, TypedDict


class DCFSFileVersionSerialized(TypedDict, total=False):
    type: Literal["FV"]
    id: str
    updatedAt: int
    # Legacy single-part storage (backwards compat)
    messageId: int
    # Legacy multi-part storage
    messageIds: List[int]
    # Compact key name (new serialization)
    m: List[int]
    # Base64-encoded message IDs (for files with many parts)
    mb: str
    size: int
    # Legacy part-sizes storage
    partSizes: List[int]
    # Compact part-sizes key (new serialization)
    p: List[int]


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
