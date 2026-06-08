import asyncio
import io
import logging
import os
from typing import List, Optional, Sequence, Any

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

    async def _get_channel(self, channel_id: int) -> Any:
        channel = self._bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self._bot.fetch_channel(channel_id)
            except discord.NotFound:
                raise TechnicalError(f"Channel {channel_id} not found.")
            except discord.Forbidden:
                raise TechnicalError(f"Permission denied for channel {channel_id}.")
        return channel

    async def send_text(self, req: SendTextReq) -> SendMessageResp:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        msg = await channel.send(req.text)
        return SendMessageResp(message_id=msg.id)

    async def send_file(self, req: SendFileReq) -> SendMessageResp:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        f = discord.File(io.BytesIO(req.buffer), filename=req.name)
        msg = await channel.send(file=f)
        return SendMessageResp(message_id=msg.id)

    async def get_messages(self, req: GetMessagesReq) -> GetMessagesResp:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        messages: List[Optional[MessageResp]] = []
        for message_id in req.message_ids:
            try:
                msg = await channel.fetch_message(message_id)
                messages.append(self._to_message_dto(msg))
            except discord.NotFound:
                messages.append(None)
        return messages

    async def get_pinned_messages(self, req: GetPinnedMessageReq) -> GetMessagesRespNoNone:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        pins = await channel.pins()
        return [self._to_message_dto(p) for p in pins]

    async def pin_message(self, req: PinMessageReq) -> None:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        msg = await channel.fetch_message(req.message_id)
        await msg.pin()

    async def delete_messages(self, req: DeleteMessagesReq) -> None:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        if len(req.message_ids) == 1:
            msg = await channel.fetch_message(req.message_ids[0])
            await msg.delete()
            return

        to_delete = []
        for m_id in req.message_ids:
            msg = await channel.fetch_message(m_id)
            to_delete.append(msg)
        await channel.delete_messages(to_delete)

    async def edit_message_text(self, req: EditMessageTextReq) -> SendMessageResp:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        msg = await channel.fetch_message(req.message_id)
        await msg.edit(content=req.text)
        return SendMessageResp(message_id=msg.id)

    async def edit_message_media(self, req: EditMessageMediaReq) -> Message:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        msg = await channel.fetch_message(req.message_id)
        f = discord.File(io.BytesIO(req.buffer), filename=req.name)
        await msg.edit(attachments=[f])
        return Message(message_id=msg.id)

    async def download_file(self, req: DownloadFileReq) -> DownloadFileResp:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        msg = await channel.fetch_message(req.message_id)
        if not msg.attachments:
            raise UnDownloadableMessage(req.message_id)
        attachment = msg.attachments[0]
        
        session = await self._ensure_http_session()
        
        async def _chunk_generator():
            async with session.get(attachment.url) as response:
                current_pos = 0
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    chunk_len = len(chunk)
                    if req.begin <= current_pos + chunk_len and (req.end == -1 or current_pos <= req.end):
                        b_in_chunk = max(0, req.begin - current_pos)
                        if req.end == -1:
                            e_in_chunk = chunk_len
                        else:
                            e_in_chunk = min(chunk_len, req.end - current_pos + 1)
                        yield chunk[b_in_chunk:e_in_chunk]
                    current_pos += chunk_len

        return DownloadFileResp(chunks=_chunk_generator(), size=attachment.size)

    async def search_messages(self, req: SearchMessageReq) -> GetMessagesRespNoNone:
        channel_id = self._parse_channel_id(req.chat)
        channel = await self._get_channel(channel_id)
        matched_messages = []
        async for message in channel.history(limit=100):
            if message.content and req.search in message.content:
                matched_messages.append(self._to_message_dto(message))
            elif message.attachments and any(req.search in att.filename for att in message.attachments):
                matched_messages.append(self._to_message_dto(message))
        return matched_messages

    def _to_message_dto(self, message: discord.Message) -> MessageResp:
        doc = None
        if message.attachments:
            att = message.attachments[0]
            doc = Document(
                name=att.filename,
                size=att.size,
                mime_type=att.content_type
            )
        return MessageResp(
            message_id=message.id,
            text=message.content if message.content else "",
            document=doc
        )

    def _parse_channel_id(self, channel_id: Any) -> int:
        try:
            return int(channel_id)
        except (ValueError, TypeError):
            raise TechnicalError(
                f"Invalid channel ID: {channel_id}. Discord channel IDs are numeric."
            )

    async def resolve_channel_id(self, channel_id: str) -> int:
        return self._parse_channel_id(channel_id)

    async def _get_me(self) -> GetMeResp:
        user = self._bot.user
        if not user:
            raise TechnicalError("Bot user not found")
        return GetMeResp(
            name=user.name,
            is_premium=False,
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

    asyncio.get_event_loop()._discord_bot = bot  # type: ignore

    @bot.event
    async def on_ready():
        if bot.user is not None:
            logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    await bot.login(token)
    asyncio.create_task(bot.connect())
    await bot.wait_until_ready()

    return bot


async def login_as_bots(config: Config) -> List[discord.Client]:
    return [await login_as_bot(config)]
