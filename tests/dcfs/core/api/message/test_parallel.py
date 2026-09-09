from unittest.mock import AsyncMock, MagicMock

import pytest

from dcfs.core.api.message import MessageApi
from dcfs.reqres import DownloadFileResp


async def mock_chunks(data):
    for chunk in data:
        yield chunk


@pytest.mark.asyncio
async def test_download_file_parallel():
    discord_api = MagicMock()
    bot = AsyncMock()
    discord_api.next_bot = bot
    message_api = MessageApi(discord_api, private_file_channel=123)

    # Return different chunk data for each sub-range request
    bot.download_file.side_effect = [
        DownloadFileResp(chunks=mock_chunks([b"part1_chunk1", b"part1_chunk2"]), size=10),
        DownloadFileResp(chunks=mock_chunks([b"part2_chunk1"]), size=10),
        DownloadFileResp(chunks=mock_chunks([b"part3_chunk1"]), size=10),
        DownloadFileResp(chunks=mock_chunks([b"part4_chunk1"]), size=10),
    ]

    resp = await message_api.download_file_parallel(message_id=999, begin=0, end=39)

    chunks = []
    async for chunk in resp.chunks:
        chunks.append(chunk)

    assert chunks == [
        b"part1_chunk1",
        b"part1_chunk2",
        b"part2_chunk1",
        b"part3_chunk1",
        b"part4_chunk1",
    ]
    assert bot.download_file.call_count == 4
