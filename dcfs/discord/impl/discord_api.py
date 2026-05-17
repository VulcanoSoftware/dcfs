"""
Discord-based storage backend for DCFS.

Discord API is used directly via aiohttp (no discord.py library required).
Each Discord channel acts as a "channel" where files are uploaded as attachments.

Discord limits:
  - Max attachment size: 25 MB (free), 500 MB (Nitro/boosted servers)
  - Messages can have content (text) and up to 10 attachments
  - Pinned messages: up to 50 per channel

File storage strategy:
  - Text messages: used for file descriptors (JSON stored in message content)
  - File messages: files uploaded as attachments, one attachment per message
  - Metadata: stored in a pinned message as a file attachment
  - File parts (>25 MB files): each part is a separate message with one attachment
"""

import asyncio
import io
import logging
from typing import List, Optional, Sequence

import aiohttp

from dcfs.config import Config
from dcfs.errors import TechnicalError, UnDownloadableMessage
from dcfs.reqres import (
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
    SaveBigFilePartReq,
    SaveFilePartReq,
    SaveFilePartResp,
    SearchMessageReq,
    SendFileReq,
    SendMessageResp,
    SendTextReq,
)
from dcfs.discord.interface import ITDLibClient
from dcfs.utils.message_cache import channel_cache
from dcfs.utils.others import exclude_none

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordAPI(ITDLibClient):
    """
    Discord-backed implementation of ITDLibClient.

    One DiscordAPI instance corresponds to one Discord bot token.
    The "channel" concept maps directly to a Discord channel ID.

    File upload flow (replaces Telegram's MTProto chunked upload):
      1. save_file_part / save_big_file_part: accumulate bytes in memory
      2. send_small_file / send_big_file: POST multipart/form-data to Discord

    The Telegram concept of a "file_id" (a random int) is reused here as a
    key into an in-process dict that holds the assembled bytes until send_*.
    """

    def __init__(self, token: str, session: aiohttp.ClientSession):
        super().__init__()
        self._token = token
        self._session = session
        self._headers = {
            "Authorization": f"Bot {token}",
        }
        # In-process buffer for chunked uploads.
        # key: file_id (int) -> {parts: {part_index: bytes}, total_parts: int, name: str}
        self._upload_buffers: dict[int, dict] = {}

    # ------------------------------------------------------------------ helpers

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        url = f"{DISCORD_API_BASE}{path}"
        async with self._session.request(
            method, url, headers=self._headers, **kwargs
        ) as resp:
            if resp.status == 204:
                return {}
            data = await resp.json()
            if resp.status >= 400:
                raise TechnicalError(
                    f"Discord API error {resp.status}: {data}"
                )
            return data

    @staticmethod
    def _parse_message(m: dict) -> Optional[MessageResp]:
        """Convert a raw Discord message dict to a MessageResp."""
        if not m:
            return None

        msg_id = int(m["id"])
        text = m.get("content", "") or ""
        document: Optional[Document] = None

        attachments = m.get("attachments", [])
        if attachments:
            att = attachments[0]
            size = att.get("size", 0)
            att_id = int(att["id"])
            document = Document(
                size=size,
                id=att_id,
                # Discord has no access_hash / file_reference; store URL as bytes
                access_hash=0,
                file_reference=att.get("url", "").encode(),
                mime_type=att.get("content_type"),
            )

        return MessageResp(
            message_id=msg_id,
            text=text,
            document=document,
        )

    # ------------------------------------------------------------------ ITDLibClient

    async def get_messages(self, req: GetMessagesReq) -> GetMessagesResp:
        cache = channel_cache(req.chat).id
        missing_ids = cache.find_nonexistent(req.message_ids)

        if missing_ids:
            # Discord doesn't support fetching multiple arbitrary messages in one
            # call, so we fetch them individually.
            async def fetch_one(msg_id: int):
                try:
                    raw = await self._request(
                        "GET", f"/channels/{req.chat}/messages/{msg_id}"
                    )
                    msg = self._parse_message(raw)
                    cache[msg_id] = msg
                except TechnicalError:
                    cache[msg_id] = None

            await asyncio.gather(*(fetch_one(mid) for mid in missing_ids))

        return GetMessagesResp(cache.gets(req.message_ids))

    async def send_text(self, req: SendTextReq) -> SendMessageResp:
        data = await self._request(
            "POST",
            f"/channels/{req.chat}/messages",
            json={"content": req.text},
        )
        return SendMessageResp(message_id=int(data["id"]))

    async def edit_message_text(self, req: EditMessageTextReq) -> SendMessageResp:
        channel_cache(req.chat).id[req.message_id] = None
        data = await self._request(
            "PATCH",
            f"/channels/{req.chat}/messages/{req.message_id}",
            json={"content": req.text},
        )
        return SendMessageResp(message_id=int(data["id"]))

    async def search_messages(self, req: SearchMessageReq) -> GetMessagesRespNoNone:
        cache = channel_cache(req.chat).search
        if req.search not in cache:
            # Discord's search endpoint is only available for guilds and requires
            # specific permissions. We iterate through recent messages and filter.
            # For production use, the number of messages to scan can be tuned.
            messages = await self._fetch_recent_messages(req.chat, limit=100)
            matched = [
                m for m in messages
                if m and req.search in (m.text or "")
            ]
            cache[req.search] = tuple(matched)
        return GetMessagesRespNoNone(list(cache[req.search]))

    async def _fetch_recent_messages(
        self, channel_id: int, limit: int = 100
    ) -> List[Optional[MessageResp]]:
        """Fetch up to `limit` recent messages from a channel."""
        raw_messages = await self._request(
            "GET",
            f"/channels/{channel_id}/messages",
            params={"limit": min(limit, 100)},
        )
        return [self._parse_message(m) for m in raw_messages]

    async def get_pinned_messages(
        self, req: GetPinnedMessageReq
    ) -> GetMessagesRespNoNone:
        raw_messages = await self._request(
            "GET", f"/channels/{req.chat}/pins"
        )
        return GetMessagesRespNoNone(
            list(
                exclude_none(
                    self._parse_message(m) for m in raw_messages
                )
            )
        )

    async def pin_message(self, req: PinMessageReq) -> None:
        await self._request(
            "PUT",
            f"/channels/{req.chat}/pins/{req.message_id}",
        )

    # ------------------------------------------------------------------ file upload

    def _get_buffer(self, file_id: int) -> dict:
        if file_id not in self._upload_buffers:
            self._upload_buffers[file_id] = {
                "parts": {},
                "total_parts": None,
                "name": "file",
            }
        return self._upload_buffers[file_id]

    def _assemble_buffer(self, file_id: int) -> bytes:
        buf = self._upload_buffers.pop(file_id, {})
        parts = buf.get("parts", {})
        sorted_parts = [parts[i] for i in sorted(parts.keys())]
        return b"".join(sorted_parts)

    async def save_file_part(self, req: SaveFilePartReq) -> SaveFilePartResp:
        buf = self._get_buffer(req.file_id)
        buf["parts"][req.file_part] = req.bytes
        return SaveFilePartResp(success=True)

    async def save_big_file_part(self, req: SaveBigFilePartReq) -> SaveFilePartResp:
        buf = self._get_buffer(req.file_id)
        buf["parts"][req.file_part] = req.bytes
        buf["total_parts"] = req.file_total_parts
        return SaveFilePartResp(success=True)

    async def _send_file_attachment(
        self,
        channel_id: int,
        file_data: bytes,
        file_name: str,
        caption: str = "",
    ) -> SendMessageResp:
        form = aiohttp.FormData()
        if caption:
            form.add_field("content", caption)
        form.add_field(
            "files[0]",
            io.BytesIO(file_data),
            filename=file_name,
            content_type="application/octet-stream",
        )
        data = await self._request(
            "POST",
            f"/channels/{channel_id}/messages",
            data=form,
        )
        return SendMessageResp(message_id=int(data["id"]))

    async def send_small_file(self, req: SendFileReq) -> SendMessageResp:
        file_data = self._assemble_buffer(req.file.id)
        return await self._send_file_attachment(
            req.chat, file_data, req.file.name, caption=req.caption
        )

    async def send_big_file(self, req: SendFileReq) -> SendMessageResp:
        # Same as small file for Discord - data is already assembled in memory
        file_data = self._assemble_buffer(req.file.id)
        return await self._send_file_attachment(
            req.chat, file_data, req.file.name, caption=req.caption
        )

    async def edit_message_media(self, req: EditMessageMediaReq) -> Message:
        """
        Discord doesn't support editing a message's attachment in-place.
        Instead, we delete the old message and send a new one, then return
        the new message ID.

        Note: callers that store message_id references (e.g. metadata pinned
        message) will receive the updated ID via the return value.
        """
        channel_cache(req.chat).id[req.message_id] = None

        # Delete old message
        try:
            await self._request(
                "DELETE",
                f"/channels/{req.chat}/messages/{req.message_id}",
            )
        except TechnicalError as e:
            logger.warning(f"Could not delete message {req.message_id}: {e}")

        # Send new message with the updated file
        file_data = self._assemble_buffer(req.file.id)
        resp = await self._send_file_attachment(
            req.chat, file_data, req.file.name
        )
        return Message(message_id=resp.message_id)

    # ------------------------------------------------------------------ download

    async def download_file(self, req: DownloadFileReq) -> DownloadFileResp:
        # Fetch the message to get the attachment URL
        try:
            raw = await self._request(
                "GET",
                f"/channels/{req.chat}/messages/{req.message_id}",
            )
        except TechnicalError as e:
            raise UnDownloadableMessage(req.message_id) from e

        attachments = raw.get("attachments", [])
        if not attachments:
            raise UnDownloadableMessage(req.message_id)

        url = attachments[0]["url"]
        total_size = attachments[0].get("size", 0)

        bytes_to_read = req.end - req.begin + 1

        # Use HTTP Range requests for partial downloads
        range_header = f"bytes={req.begin}-{req.end}"

        async def chunks():
            chunk_size = req.chunk_size * 1024
            async with self._session.get(
                url,
                headers={"Range": range_header},
            ) as resp:
                if resp.status not in (200, 206):
                    raise TechnicalError(
                        f"Failed to download file: HTTP {resp.status}"
                    )
                remaining = bytes_to_read
                async for chunk in resp.content.iter_chunked(chunk_size):
                    if remaining <= 0:
                        break
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]
                    yield chunk
                    remaining -= len(chunk)

        return DownloadFileResp(chunks=chunks(), size=bytes_to_read)

    # ------------------------------------------------------------------ identity

    async def resolve_channel_id(self, channel_id: str) -> int:
        return int(channel_id)

    async def _get_me(self) -> GetMeResp:
        data = await self._request("GET", "/users/@me")
        name = data.get("global_name") or data.get("username", "unknown")
        return GetMeResp(
            name=f"@{data.get('username', name)}",
            is_premium=False,  # Discord has no "premium" equivalent affecting file size here
        )


async def login(config: Config) -> List[DiscordAPI]:
    """
    Create DiscordAPI instances for all configured bot tokens.
    Returns a list so that the round-robin TDLibApi still works,
    even though Discord doesn't need multi-bot workarounds like Telegram.
    """
    session = aiohttp.ClientSession()
    tokens = config.discord.bot_tokens

    clients = []
    for token in tokens:
        client = DiscordAPI(token=token, session=session)
        me = await client.get_me()
        logger.info(f"Discord bot logged in as {me.name}")
        clients.append(client)

    return clients
