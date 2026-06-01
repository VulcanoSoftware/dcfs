import asyncio
import logging
from dataclasses import dataclass
from functools import reduce
from typing import List, Optional, Set

from dcfs.reqres import GetMessagesReq, GetMessagesResp, MessageResp
from dcfs.discord.interface import DiscordApi
from dcfs.utils.message_cache import channel_cache

DELAY = 0.5
BOTS_COUNT = 1  # Discord uses a single bot


logger = logging.getLogger(__name__)


@dataclass
class Request:
    ids: list[int]
    future: asyncio.Future[GetMessagesResp]


class MessageBroker:
    def __init__(self, discord_api: DiscordApi, private_file_channel: int):
        self.discord_api = discord_api
        self.__requests: List[Request] = []
        self.__lock = asyncio.Lock()
        self.__task: Optional[asyncio.Task] = None
        self.private_file_channel = private_file_channel

    async def get_messages(self, ids: list[int]) -> list[Optional[MessageResp]]:
        if cached_messages := channel_cache(self.private_file_channel).id.gets(ids):
            if all(msg is not None for msg in cached_messages):
                return cached_messages

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async with self.__lock:
            self.__requests.append(Request(ids, future))
            if self.__task and not self.__task.done():
                self.__task.cancel()
            self.__task = loop.create_task(self.process_requests())
        return await future

    async def process_requests(self):
        await asyncio.sleep(DELAY)
        async with self.__lock:
            requests, self.__requests = self.__requests, []

        if not requests:
            return

        ids: Set[int] = reduce(lambda full, req: full.union(req.ids), requests, set())

        e: Optional[Exception] = None
        bot = self.discord_api.next_bot
        for i in range(BOTS_COUNT):
            try:

                messages = await bot.get_messages(
                    GetMessagesReq(
                        chat=self.private_file_channel, message_ids=tuple(ids)
                    )
                )

                messages_map = {
                    msg.message_id: msg for msg in messages if msg is not None
                }

                for r in requests:
                    if not r.future.done():
                        r.future.set_result(
                            [messages_map.get(msg_id) for msg_id in r.ids]
                        )
                return
            except asyncio.CancelledError:
                pass
            except Exception as ex:
                e = ex
                me = await bot.get_me()
                logger.error(
                    f"{me.name} failed to get messages: {ex}, retrying..."
                )
                bot = self.discord_api.next_bot
        if not e:
            return

        logger.error(
            "Bot failed to get messages, propagating exception to all requests."
        )
        for request in requests:
            if e and not request.future.done():
                request.future.set_exception(e)
