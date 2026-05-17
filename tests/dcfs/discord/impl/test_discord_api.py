"""
Tests for the Discord storage backend implementation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from aiohttp import ClientSession

from dcfs.discord.impl.discord_api import DiscordAPI
from dcfs.reqres import (
    GetMessagesReq,
    SendTextReq,
    EditMessageTextReq,
    SearchMessageReq,
    GetPinnedMessageReq,
    PinMessageReq,
    SaveFilePartReq,
    SaveBigFilePartReq,
    SendFileReq,
    DownloadFileReq,
    UploadedFile,
)
from dcfs.errors import TechnicalError, UnDownloadableMessage


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=ClientSession)
    return session


@pytest.fixture
def discord_api(mock_session):
    return DiscordAPI(token="Bot test_token", session=mock_session)


@pytest.fixture
def mock_channel_id():
    return 123456789


@pytest.fixture
def mock_message_id():
    return 987654321


class TestGetMessages:
    async def test_get_single_message(self, discord_api, mock_channel_id, mock_message_id, mocker):
        raw_message = {
            "id": str(mock_message_id),
            "content": "hello",
            "attachments": [],
        }
        mocker.patch.object(discord_api, "_request", new=AsyncMock(return_value=raw_message))
        mocker.patch("dcfs.discord.impl.discord_api.channel_cache")

        req = GetMessagesReq(chat=mock_channel_id, message_ids=(mock_message_id,))
        result = await discord_api.get_messages(req)
        assert len(result) == 1

    async def test_get_message_with_attachment(self, discord_api, mock_channel_id, mock_message_id, mocker):
        raw_message = {
            "id": str(mock_message_id),
            "content": "",
            "attachments": [
                {
                    "id": "111",
                    "size": 1024,
                    "url": "https://cdn.discordapp.com/attachments/test/file.bin",
                    "content_type": "application/octet-stream",
                }
            ],
        }
        mocker.patch.object(discord_api, "_request", new=AsyncMock(return_value=raw_message))
        mocker.patch("dcfs.discord.impl.discord_api.channel_cache")

        req = GetMessagesReq(chat=mock_channel_id, message_ids=(mock_message_id,))
        result = await discord_api.get_messages(req)
        assert result[0] is not None
        assert result[0].document is not None
        assert result[0].document.size == 1024


class TestSendText:
    async def test_send_text(self, discord_api, mock_channel_id, mocker):
        mocker.patch.object(discord_api, "_request", new=AsyncMock(return_value={"id": "999"}))
        req = SendTextReq(chat=mock_channel_id, text="test message")
        result = await discord_api.send_text(req)
        assert result.message_id == 999


class TestSaveFilePart:
    async def test_save_file_part(self, discord_api):
        req = SaveFilePartReq(file_id=42, bytes=b"hello", file_part=0)
        result = await discord_api.save_file_part(req)
        assert result.success is True
        assert discord_api._upload_buffers[42]["parts"][0] == b"hello"

    async def test_save_big_file_part(self, discord_api):
        req = SaveBigFilePartReq(file_id=42, bytes=b"world", file_part=1, file_total_parts=3)
        result = await discord_api.save_big_file_part(req)
        assert result.success is True
        assert discord_api._upload_buffers[42]["total_parts"] == 3


class TestSendFile:
    async def test_send_small_file(self, discord_api, mock_channel_id, mocker):
        # Pre-populate buffer
        discord_api._upload_buffers[1] = {"parts": {0: b"data"}, "total_parts": 1, "name": "test.bin"}

        mocker.patch.object(discord_api, "_send_file_attachment", new=AsyncMock(return_value=MagicMock(message_id=555)))

        req = SendFileReq(
            chat=mock_channel_id,
            file=UploadedFile(id=1, parts=1, name="test.bin"),
            name="test.bin",
            caption="",
        )
        result = await discord_api.send_small_file(req)
        assert result.message_id == 555


class TestGetMe:
    async def test_get_me(self, discord_api, mocker):
        mocker.patch.object(discord_api, "_request", new=AsyncMock(return_value={
            "id": "123",
            "username": "testbot",
            "global_name": "Test Bot",
        }))
        result = await discord_api._get_me()
        assert result.name == "@testbot"
        assert result.is_premium is False


class TestResolveChannelId:
    async def test_resolve_integer_id(self, discord_api):
        result = await discord_api.resolve_channel_id("123456789")
        assert result == 123456789

    async def test_resolve_non_integer_raises(self, discord_api):
        with pytest.raises(ValueError):
            await discord_api.resolve_channel_id("not-a-number")
