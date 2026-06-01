import asyncio
import io
import logging
import os
from typing import List, Optional, Sequence

import aiohttp
import discord

from dcfs.config import Config
from dcfs.errors import TechnicalError, UnDownloadableMessage
from dcfs.reqres import (
    DeleteMessagesReq,
    Document,
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
    MessageResp,
    PinMessageReq,
    SearchMessageReq,
    SendFileReq,
    SendMessageResp,
    SendTextReq,
)
from dcfs.discord.interface import IDiscordClient
from dcfs.utils.message_cache import channel_cache
from dcfs.utils.others import exclude_none

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for downloads


class DiscordBotAPI(IDiscordClient):
    def __init__(self, bot: discord.Client, bot_token: str):
        super().__init__()
        self._bot = bot
        self._bot_token = bot_token
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _ensure_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    @staticmethod
    def _get_channel(channel_id: int) -> discord.TextChannel:
        """Get a text channel by ID. Raises if not found."""
        from dcfs.config import get_config

        config = get_config()
        guild_id = config.discord.guild_id
        # Try to get from the bot's cache
        if guild_id:
            guild = discord.utils.get(
                asyncio.get_event_loop()._discord_bot.guilds, id=guild_id  # type: ignore
            )
            if guild:
                channel = guild.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    return channel

        # Fallback: try direct fetch
        bot = asyncio.get_event_loop()._discord_bot  # type: ignore
        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            raise TechnicalError(f"Channel {channel_id} is not a text channel or not found")
        return channel

    @staticmethod
    def _transform_messages(
        messages: Sequence[discord.Message],
    ) -> GetMessagesResp:
        res = GetMessagesResp()

        for m in messages:
            if not m:
                res.append(None)
                continue

            document = None
            if m.attachments:
                attachment = m.attachments[0]
                document = Document(
                    size=attachment.size,
                    id=attachment.id,
                    access_hash=0,
                    file_reference=b"",
                    mime_type=attachment.content_type or "application/octet-stream",
                )

            message_resp = MessageResp(
                message_id=m.id,
                text=m.content or "",
                document=document,
            )
            res.append(message_resp)
        return res

    async def get_messages(self, req: GetMessagesReq) -> GetMessagesResp:
        cache = channel_cache(req.chat).id
        if message_id_to_fetch := cache.find_nonexistent(list(req.message_ids)):
            channel = self._get_channel(req.chat)
            fetched: List[discord.Message] = []
            for mid in message_id_to_fetch:
                try:
                    msg = await channel.fetch_message(mid)
                    fetched.append(msg)
                except (discord.NotFound, discord.Forbidden):
                    fetched.append(None)  # type: ignore

            for message in exclude_none(self._transform_messages(fetched)):
                cache[message.message_id] = message

        return GetMessagesResp(cache.gets(list(req.message_ids)))

    async def send_text(self, req: SendTextReq) -> SendMessageResp:
        channel = self._get_channel(req.chat)
        message = await channel.send(content=req.text)
        return SendMessageResp(message_id=message.id)

    async def edit_message_text(self, req: EditMessageTextReq) -> SendMessageResp:
        cache = channel_cache(req.chat).id
        cache[req.message_id] = None
        channel = self._get_channel(req.chat)
        try:
            msg = await channel.fetch_message(req.message_id)
            await msg.edit(content=req.text)
        except discord.NotFound:
            # Message was deleted, create a new one
            new_msg = await channel.send(content=req.text)
            return SendMessageResp(message_id=new_msg.id)
        return SendMessageResp(message_id=req.message_id)

    async def search_messages(self, req: SearchMessageReq) -> GetMessagesRespNoNone:
        cache = channel_cache(req.chat).search
        if req.search not in cache:
            channel = self._get_channel(req.chat)
            result: List[discord.Message] = []
            async for msg in channel.history(limit=100):
                if req.search in (msg.content or ""):
                    result.append(msg)
            cache[req.search] = tuple(
                exclude_none(self._transform_messages(result))
            )
        return GetMessagesRespNoNone(list(cache[req.search]))

    async def get_pinned_messages(
        self, req: GetPinnedMessageReq
    ) -> GetMessagesRespNoNone:
        channel = self._get_channel(req.chat)
        pinned = await channel.pins()
        return list(exclude_none(self._transform_messages(pinned)))

    async def pin_message(self, req: PinMessageReq) -> None:
        channel = self._get_channel(req.chat)
        msg = await channel.fetch_message(req.message_id)
        await msg.pin()

    async def send_file(self, req: SendFileReq) -> SendMessageResp:
        channel = self._get_channel(req.chat)
        # For Discord, we send files as attachments
        file = discord.File(
            io.BytesIO(req.buffer),
            filename=req.name,
        )
        message = await channel.send(
            content=req.caption or "",
            file=file,
        )
        # Store the attachment size in the message for later retrieval
        if message.attachments:
            return SendMessageResp(
                message_id=message.id,
                size=message.attachments[0].size,
            )
        return SendMessageResp(message_id=message.id, size=len(req.buffer))

    async def edit_message_media(self, req: EditMessageMediaReq) -> Message:
        cache = channel_cache(req.chat).id
        cache[req.message_id] = None
        channel = self._get_channel(req.chat)
        msg = await channel.fetch_message(req.message_id)
        # Discord doesn't support editing attachments, so we send a new message
        # and delete the old one
        file = discord.File(
            io.BytesIO(req.buffer),
            filename=req.name,
        )
        new_msg = await channel.send(file=file)
        await msg.delete()
        return Message(message_id=new_msg.id)

    async def download_file(self, req: DownloadFileReq) -> DownloadFileResp:
        channel = self._get_channel(req.chat)
        try:
            msg = await channel.fetch_message(req.message_id)
        except discord.NotFound:
            raise UnDownloadableMessage(req.message_id)

        if not msg.attachments:
            raise UnDownloadableMessage(req.message_id)

        attachment = msg.attachments[0]
        bytes_to_read = req.end - req.begin + 1

        session = await self._ensure_http_session()

        headers = {"Range": f"bytes={req.begin}-{req.end}"} if req.end >= req.begin else {}

        async def chunks():
            async with session.get(attachment.url, headers=headers) as resp:
                rest = bytes_to_read
                async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                    if len(chunk) > rest:
                        chunk = chunk[:rest]
                    yield chunk
                    rest -= len(chunk)
                    if rest <= 0:
                        break

        return DownloadFileResp(chunks=chunks(), size=bytes_to_read)

    async def delete_messages(self, req: DeleteMessagesReq) -> None:
        if not req.message_ids:
            return
        cache = channel_cache(req.chat).id
        for mid in req.message_ids:
            cache[mid] = None
        channel = self._get_channel(req.chat)
        for mid in req.message_ids:
            try:
                msg = await channel.fetch_message(mid)
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

    async def resolve_channel_id(self, channel_id: str) -> int:
        try:
            return int(channel_id)
        except ValueError:
            raise TechnicalError(
                f"Invalid channel ID: {channel_id}. Discord channel IDs are numeric."
            )

    async def _get_me(self) -> GetMeResp:
        user = self._bot.user
        if not user:
            raise TechnicalError("Bot user not found")
        return GetMeResp(
            name=user.name,
            is_premium=False,  # Discord doesn't have a premium concept for bots
        )

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()


async def login_as_bot(config: Config) -> discord.Client:
    """Create and start a Discord bot client."""
    token = config.discord.bot_token

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = discord.Client(intents=intents)

    # Store bot reference for later use
    asyncio.get_event_loop()._discord_bot = bot  # type: ignore

    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Start the bot in the background
    asyncio.create_task(bot.start(token))

    # Wait for the bot to be ready
    await bot.wait_until_ready()

    return bot


async def login_as_bots(config: Config) -> List[discord.Client]:
    """Login with a single Discord bot (Discord only supports one bot connection)."""
    bot = await login_as_bot(config)
    return [bot]
