import asyncio
import logging
from typing import Iterable, Iterator, List

from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate

from dcfs.config import get_config
from dcfs.errors import (
    MessageNotFound,
    TechnicalError,
)
from dcfs.reqres import (
    DeleteMessagesReq,
    DownloadFileReq,
    DownloadFileResp,
    EditMessageTextReq,
    GetPinnedMessageReq,
    MessageResp,
    PinMessageReq,
    SearchMessageReq,
    SendTextReq,
)
from dcfs.discord.interface import DiscordApi
from dcfs.utils.chained_async_iterator import ChainedAsyncIterator
from dcfs.utils.others import exclude_none, is_big_file

from .message_broker import MessageBroker

logger = logging.getLogger(__name__)

# Discord's bulk delete caps at 100 messages per request.
DELETE_BATCH_SIZE = 100

rate = Rate(20, Duration.SECOND)
bucket = InMemoryBucket([rate])
limiter = Limiter(bucket, max_delay=60 * 1000)  # 60 seconds max delay


class MessageApi(MessageBroker):
    def __init__(self, discord_api: DiscordApi, private_file_channel: int):
        super().__init__(discord_api, private_file_channel)

    @staticmethod
    def __try_acquire(name: str):
        limiter.try_acquire(name)

    async def send_text(self, message: str) -> int:
        self.__try_acquire("MessageApi.send_text")
        return (
            await self.discord_api.next_bot.send_text(
                SendTextReq(chat=self.private_file_channel, text=message)
            )
        ).message_id

    async def edit_message_text(self, message_id: int, message: str) -> int:
        self.__try_acquire("MessageApi.edit_message_text")
        try:
            return (
                await self.discord_api.next_bot.edit_message_text(
                    EditMessageTextReq(
                        chat=self.private_file_channel,
                        message_id=message_id,
                        text=message,
                    )
                )
            ).message_id
        except Exception:
            return message_id

    async def delete_messages(self, message_ids: Iterable[int]) -> None:
        """Best-effort deletion of channel messages.

        Gated by ``discord.delete_messages_on_remove`` so the default
        DCFS behavior (file removed from metadata, message kept on the
        channel) is unchanged. Failures are logged but never raised --
        the caller has already committed the metadata change and we do
        not want a delete error to roll that back.
        """
        if not get_config().discord.delete_messages_on_remove:
            return
        unique_ids: List[int] = list({mid for mid in message_ids if mid > 0})
        if not unique_ids:
            return
        for start in range(0, len(unique_ids), DELETE_BATCH_SIZE):
            batch = tuple(unique_ids[start : start + DELETE_BATCH_SIZE])
            self.__try_acquire("MessageApi.delete_messages")
            try:
                await self.discord_api.next_bot.delete_messages(
                    DeleteMessagesReq(
                        chat=self.private_file_channel,
                        message_ids=batch,
                    )
                )
            except Exception as ex:
                logger.warning(
                    f"Failed to delete discord messages {batch} from channel "
                    f"{self.private_file_channel}: {ex}"
                )

    async def pin_message(self, message_id: int):
        self.__try_acquire("MessageApi.pin_message")
        return await self.discord_api.next_bot.pin_message(
            PinMessageReq(chat=self.private_file_channel, message_id=message_id)
        )

    async def get_pinned_messages(self) -> list[MessageResp]:
        self.__try_acquire("MessageApi.get_pinned_messages")
        return await self.discord_api.next_bot.get_pinned_messages(
            GetPinnedMessageReq(chat=self.private_file_channel)
        )

    async def search_messages(self, search: str) -> list[MessageResp]:
        self.__try_acquire("MessageApi.search_messages")
        bot = self.discord_api.next_bot
        return list(
            exclude_none(
                await bot.search_messages(
                    SearchMessageReq(chat=self.private_file_channel, search=search)
                )
            )
        )

    @classmethod
    def split_download_tasks(
        cls, begin: int, end: int, n: int
    ) -> Iterator[tuple[int, int]]:
        length = end - begin + 1
        length_per_chunk = length // n

        for i in range(n - 1):
            b = begin + i * length_per_chunk
            e = b + length_per_chunk - 1
            yield b, e

        yield begin + (n - 1) * length_per_chunk, end

    @staticmethod
    def _size(begin: int, end: int) -> int:
        return begin - end + 1

    async def download_file_parallel(self, message_id: int, begin: int, end: int):
        tasks = [
            self.discord_api.next_bot.download_file(
                DownloadFileReq(
                    chat=self.private_file_channel,
                    message_id=message_id,
                    chunk_size=get_config().dcfs.download.chunk_size_kb,
                    begin=b,
                    end=e,
                )
            )
            for b, e in self.split_download_tasks(begin, end, 1)  # Single bot, no parallel
        ]

        res = [t.chunks for t in await asyncio.gather(*tasks)]
        return DownloadFileResp(
            chunks=ChainedAsyncIterator(res), size=self._size(begin, end)
        )

    async def download_file(
        self, message_id: int, begin: int, end: int
    ) -> DownloadFileResp:
        if end > 0 and is_big_file(self._size(begin, end)):
            return await self.download_file_parallel(message_id, begin, end)

        return await self.discord_api.next_bot.download_file(
            DownloadFileReq(
                chat=self.private_file_channel,
                message_id=message_id,
                chunk_size=get_config().dcfs.download.chunk_size_kb,
                begin=begin,
                end=end,
            )
        )
