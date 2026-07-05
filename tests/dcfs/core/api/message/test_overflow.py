import pytest
from unittest.mock import AsyncMock, MagicMock
from dcfs.core.api.message import MessageApi, OVERFLOW_SENTINEL, OVERFLOW_FILENAME
from dcfs.reqres import SendMessageResp, MessageResp, Document

@pytest.mark.asyncio
async def test_send_text_overflow(mocker):
    # Setup
    discord_api = MagicMock()
    bot = AsyncMock()
    discord_api.next_bot = bot
    message_api = MessageApi(discord_api, private_file_channel=123)

    # Large message > 4000 chars
    large_text = "a" * 4001
    bot.send_file.return_value = SendMessageResp(message_id=999)

    # Execute
    msg_id = await message_api.send_text(large_text)

    # Verify
    assert msg_id == 999
    bot.send_file.assert_called_once()
    args, _ = bot.send_file.call_args
    req = args[0]
    assert req.chat == 123
    assert req.name == OVERFLOW_FILENAME
    assert req.caption == OVERFLOW_SENTINEL
    assert req.buffer == large_text.encode("utf-8")

@pytest.mark.asyncio
async def test_get_text_overflow(mocker):
    # Setup
    discord_api = MagicMock()
    bot = AsyncMock()
    discord_api.next_bot = bot
    message_api = MessageApi(discord_api, private_file_channel=123)

    overflow_text = "this is a very large message content"

    # Mock download_file (which is called by get_text for overflowed messages)
    async def mock_chunks():
        yield overflow_text.encode("utf-8")

    mock_download = mocker.patch.object(
        message_api,
        "download_file",
        return_value=AsyncMock(chunks=mock_chunks())
    )

    message = MessageResp(
        message_id=999,
        text=OVERFLOW_SENTINEL,
        document=Document(name=OVERFLOW_FILENAME, size=len(overflow_text))
    )

    # Execute
    retrieved_text = await message_api.get_text(message)

    # Verify
    assert retrieved_text == overflow_text
    mock_download.assert_called_once_with(999, 0, -1)

@pytest.mark.asyncio
async def test_get_text_normal(mocker):
    # Setup
    discord_api = MagicMock()
    message_api = MessageApi(discord_api, private_file_channel=123)

    message = MessageResp(
        message_id=999,
        text="normal message",
        document=None
    )

    # Execute
    retrieved_text = await message_api.get_text(message)

    # Verify
    assert retrieved_text == "normal message"
