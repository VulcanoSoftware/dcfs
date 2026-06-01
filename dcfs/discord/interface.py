from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from itertools import cycle
from typing import Optional, Sequence

from dcfs.reqres import (
    DeleteMessagesReq,
    DownloadFileReq,
    DownloadFileResp,
    EditMessageMediaReq,
    EditMessageTextReq,
    GetMeResp,
    GetMessagesReq,
    GetMessagesResp,
    GetMessagesRespNoNone,
    GetPinnedMessageReq,
    Message,
    PinMessageReq,
    SearchMessageReq,
    SendFileReq,
    SendMessageResp,
    SendTextReq,
)


class IDiscordClient(metaclass=ABCMeta):
    def __init__(self):
        self._me: Optional[GetMeResp] = None

    @abstractmethod
    async def get_messages(self, req: GetMessagesReq) -> GetMessagesResp:
        pass

    @abstractmethod
    async def send_text(self, req: SendTextReq) -> SendMessageResp:
        pass

    @abstractmethod
    async def edit_message_text(self, req: EditMessageTextReq) -> SendMessageResp:
        pass

    @abstractmethod
    async def search_messages(self, req: SearchMessageReq) -> GetMessagesRespNoNone:
        pass

    @abstractmethod
    async def get_pinned_messages(
        self, req: GetPinnedMessageReq
    ) -> GetMessagesRespNoNone:
        pass

    @abstractmethod
    async def pin_message(self, req: PinMessageReq) -> None:
        pass

    @abstractmethod
    async def send_file(self, req: SendFileReq) -> SendMessageResp:
        pass

    @abstractmethod
    async def edit_message_media(self, req: EditMessageMediaReq) -> Message:
        pass

    @abstractmethod
    async def download_file(self, req: DownloadFileReq) -> DownloadFileResp:
        pass

    @abstractmethod
    async def delete_messages(self, req: DeleteMessagesReq) -> None:
        pass

    @abstractmethod
    async def resolve_channel_id(self, channel_id: str) -> int:
        pass

    @abstractmethod
    async def _get_me(self) -> GetMeResp:
        pass

    async def get_me(self) -> GetMeResp:
        if self._me is None:
            self._me = await self._get_me()
        return self._me


@dataclass
class DiscordApi:
    bots: Sequence[IDiscordClient]
    account: Optional[IDiscordClient] = None

    def __post_init__(self):
        self.__bots_cycle = cycle(self.bots)

    @property
    def bot(self) -> IDiscordClient:
        return self.bots[0]

    @property
    def next_bot(self) -> IDiscordClient:
        return next(self.__bots_cycle)
