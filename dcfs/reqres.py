import os
from collections import deque
from dataclasses import dataclass, field
from io import IOBase
from typing import AsyncIterator, Optional, Tuple

from dcfs.tasks.integrations import TaskTracker


@dataclass
class Message:
    message_id: int


@dataclass
class SentFileMessage(Message):
    size: int


@dataclass
class Chat:
    chat: int


@dataclass
class GetMessagesReq(Chat):
    message_ids: Tuple[int, ...]


@dataclass
class Document:
    name: str
    size: int
    id: Optional[int] = None
    access_hash: Optional[int] = None
    file_reference: Optional[bytes] = None
    mime_type: Optional[str] = None


@dataclass
class MessageResp(Message):
    text: str
    document: Optional[Document]


@dataclass
class MessageRespWithDocument(MessageResp):
    document: Document


GetMessagesResp = list[Optional[MessageResp]]
GetMessagesRespNoNone = list[MessageResp]


@dataclass
class SearchMessageReq(Chat):
    search: str


@dataclass
class DeleteMessagesReq(Chat):
    message_ids: Tuple[int, ...]


GetPinnedMessageReq = Chat
SendMessageResp = Message


@dataclass
class SendTextReq(Chat):
    text: str


@dataclass
class EditMessageTextReq(SendTextReq, Message):
    pass


@dataclass
class PinMessageReq(Chat, Message):
    pass


@dataclass
class FileAttr:
    name: str
    caption: str


@dataclass
class SendFileReq(Chat, FileAttr):
    buffer: bytes


@dataclass
class EditMessageMediaReq(Chat, Message):
    buffer: bytes
    name: str


@dataclass
class DownloadFileReq(Chat, Message):
    chunk_size: int
    begin: int
    end: int


FileContent = AsyncIterator[bytes]


@dataclass
class DownloadFileResp:
    chunks: FileContent
    size: int


@dataclass
class GetMeResp:
    is_premium: bool
    name: str


@dataclass
class FileTags:
    pass


@dataclass
class FileMessage:
    name: str
    size: int


@dataclass
class UploadableFileMessage(FileMessage):
    caption: str
    tags: FileTags
    _offset: int
    _read_size: int

    task_tracker: Optional[TaskTracker]

    def _get_size(self) -> int:
        return 0

    def get_size(self) -> int:
        return self.size or self._get_size()

    async def open(self) -> None:
        pass

    async def read(self, length: int) -> bytes:
        raise NotImplementedError("Subclasses must implement the read method")

    async def close(self) -> None:
        pass

    def file_name(self) -> str:
        return self.name or "unnamed"

    def next_part(self, part_size: int) -> None:
        self._offset += part_size
        self._read_size = 0


@dataclass
class FileMessageEmpty(FileMessage):
    @classmethod
    def new(cls, name: str = "unnamed") -> "FileMessageEmpty":
        return cls(name=name, size=0)


@dataclass
class FileMessageFromPath(UploadableFileMessage):
    path: str
    _fd: IOBase

    def _get_size(self) -> int:
        return os.path.getsize(self.path)

    @classmethod
    def new(cls, path: str, name: str = "unnamed") -> "FileMessageFromPath":
        return cls(
            name=name,
            caption="",
            tags=FileTags(),
            path=path,
            _offset=0,
            size=os.path.getsize(path),
            task_tracker=None,
            _read_size=0,
            _fd=open(path, "rb"),
        )

    async def read(self, length: int) -> bytes:
        return self._fd.read(length)

    async def close(self) -> None:
        if self._fd:
            self._fd.close()

    def file_name(self) -> str:
        return self.name or os.path.basename(self.path)


@dataclass
class FileMessageFromBuffer(UploadableFileMessage):
    buffer: bytes
    __buffer: bytes = b""

    def _get_size(self) -> int:
        return len(self.buffer)

    @classmethod
    def new(cls, buffer: bytes, name: str = "unnamed") -> "FileMessageFromBuffer":
        return cls(
            name=name,
            caption="",
            tags=FileTags(),
            buffer=buffer,
            _offset=0,
            size=len(buffer),
            task_tracker=None,
            _read_size=0,
        )

    async def open(self) -> None:
        self.__buffer = self.buffer[self._offset :]

    async def read(self, length: int) -> bytes:
        chunk = self.__buffer[:length]
        self.__buffer = self.__buffer[length:]
        return chunk


@dataclass
class FileMessageFromStream(UploadableFileMessage):
    stream: FileContent
    cached_chunks: deque[bytes] = field(default_factory=deque)
    cached_size: int = 0

    @classmethod
    def new(
        cls,
        stream: FileContent,
        size: int,
        name: str = "unnamed",
    ) -> "FileMessageFromStream":
        return cls(
            name=name,
            caption="",
            tags=FileTags(),
            stream=stream,
            _offset=0,
            size=size,
            task_tracker=None,
            _read_size=0,
        )

    async def read(self, length: int) -> bytes:
        size_to_return = min(length, self.get_size() - self._read_size)
        if size_to_return <= 0:
            return b""

        while self.cached_size < size_to_return:
            try:
                chunk = await anext(self.stream)
            except StopAsyncIteration:
                break
            if not chunk:
                continue
            self.cached_chunks.append(chunk)
            self.cached_size += len(chunk)

        if self.cached_size <= 0:
            return b""

        size_to_return = min(size_to_return, self.cached_size)
        out = bytearray()
        remaining = size_to_return

        while remaining > 0 and self.cached_chunks:
            chunk = self.cached_chunks.popleft()
            if len(chunk) <= remaining:
                out.extend(chunk)
                remaining -= len(chunk)
                self.cached_size -= len(chunk)
            else:
                out.extend(chunk[:remaining])
                self.cached_chunks.appendleft(chunk[remaining:])
                self.cached_size -= remaining
                remaining = 0

        self._read_size += len(out)
        return bytes(out)


@dataclass
class FileMessageImported(FileMessage):
    message_id: int

    @classmethod
    def new(
        cls, message_id: int, size: int, name: str = "unnamed"
    ) -> "FileMessageImported":
        return cls(name=name, size=size, message_id=message_id)
