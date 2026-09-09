import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from dcfs.discord.impl.discord_bot import DiscordBotAPI, _url_expiry


def _channel(url: str = "https://cdn.example/file.bin", size: int = 10):
    attachment = MagicMock()
    attachment.url = url
    attachment.size = size
    message = MagicMock()
    message.attachments = [attachment]

    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=message)
    return channel


def test_url_expiry_parses_signed_urls():
    assert _url_expiry("https://cdn.example/f.bin?ex=68b0a1c0&is=1") == float(
        0x68B0A1C0
    )
    assert _url_expiry("https://cdn.example/f.bin") is None
    assert _url_expiry("https://cdn.example/f.bin?ex=zzz") is None


@pytest.mark.asyncio
async def test_concurrent_lookups_share_a_single_fetch():
    api = DiscordBotAPI(MagicMock(), "token")
    channel = _channel()

    resolved = await asyncio.gather(
        *[api._resolve_attachment(channel, 42) for _ in range(8)]
    )

    assert channel.fetch_message.await_count == 1
    assert {r.url for r in resolved} == {"https://cdn.example/file.bin"}


@pytest.mark.asyncio
async def test_cached_url_is_reused_until_it_expires():
    api = DiscordBotAPI(MagicMock(), "token")
    channel = _channel()

    await api._resolve_attachment(channel, 42)
    await api._resolve_attachment(channel, 42)
    assert channel.fetch_message.await_count == 1

    api._attachment_cache[42].expires_at = time.time() - 1
    await api._resolve_attachment(channel, 42)
    assert channel.fetch_message.await_count == 2


@pytest.mark.asyncio
async def test_cache_never_outlives_the_signed_url():
    signed_until = time.time() + 30
    api = DiscordBotAPI(MagicMock(), "token")
    channel = _channel(url=f"https://cdn.example/f.bin?ex={int(signed_until):x}")

    entry = await api._resolve_attachment(channel, 7)

    assert entry.expires_at < signed_until
