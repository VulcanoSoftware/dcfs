import asyncio
from unittest.mock import AsyncMock

import pytest

from dcfs.core.api.message import MessageApi
from dcfs.core.repository.impl.file_content import DCMsgFileContentRepository
from dcfs.core.repository.impl.file_content.file_uploader import (
    discord_max_file_size_bytes,
)
from dcfs.reqres import FileMessageFromBuffer, SendMessageResp, SentFileMessage


class TestDCMsgFileContentRepository:
    @pytest.fixture
    def mock_message_api(self, mocker):
        api = mocker.Mock(spec=MessageApi)
        api.discord_api = mocker.Mock()

        # Mock next_bot for parallel uploads
        api.discord_api.next_bot = mocker.Mock()
        api.discord_api.bot = api.discord_api.next_bot

        api.private_file_channel = 12345
        return api

    @pytest.mark.asyncio
    async def test_save_large_file_parallel(self, mock_message_api, mocker):
        # Setup: file twice the PART_SIZE
        part_size = discord_max_file_size_bytes()
        data = b"a" * (part_size * 2)
        file_msg = FileMessageFromBuffer.new(buffer=data, name="large.txt")

        # Mock next_bot.send_file to return different message IDs
        mock_message_api.discord_api.next_bot.send_file = AsyncMock(side_effect=[
            SendMessageResp(message_id=1),
            SendMessageResp(message_id=2)
        ])

        repo = DCMsgFileContentRepository(mock_message_api)

        # Call save
        sent_messages = await repo.save(file_msg)

        # Assertions
        assert len(sent_messages) == 2
        assert isinstance(sent_messages[0], SentFileMessage)
        assert sent_messages[0].message_id == 1
        assert sent_messages[0].size == part_size
        assert sent_messages[1].message_id == 2
        assert sent_messages[1].size == part_size

        # Verify send_file was called twice on the bot
        assert mock_message_api.discord_api.next_bot.send_file.call_count == 2

        # Verify call arguments
        calls = mock_message_api.discord_api.next_bot.send_file.call_args_list
        assert calls[0].args[0].name == "[part1]large.txt"
        assert len(calls[0].args[0].buffer) == part_size
        assert calls[1].args[0].name == "[part2]large.txt"
        assert len(calls[1].args[0].buffer) == part_size

    @pytest.mark.asyncio
    async def test_save_parallel_ordering(self, mock_message_api):
        """Verify that SentFileMessages are returned in the correct part order
        even if the background tasks complete out of order."""
        part_size = discord_max_file_size_bytes()
        data = b"a" * (part_size * 3)
        file_msg = FileMessageFromBuffer.new(buffer=data, name="ordered.txt")

        async def delayed_send(req):
            if "[part1]" in req.name:
                await asyncio.sleep(0.1)  # Part 1 finishes last
                return SendMessageResp(message_id=1)
            if "[part2]" in req.name:
                return SendMessageResp(message_id=2)
            return SendMessageResp(message_id=3)

        mock_message_api.discord_api.next_bot.send_file = AsyncMock(side_effect=delayed_send)

        repo = DCMsgFileContentRepository(mock_message_api, max_concurrent_parts=3)
        sent_messages = await repo.save(file_msg)

        assert len(sent_messages) == 3
        # Even though part 1 was delayed, it should still be first in the returned list
        assert [m.message_id for m in sent_messages] == [1, 2, 3]
