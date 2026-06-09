import pytest
from unittest.mock import AsyncMock, MagicMock
from dcfs.core.repository.impl.file_content import DCMsgFileContentRepository, PART_SIZE
from dcfs.core.api.message import MessageApi
from dcfs.reqres import FileMessageFromBuffer, SendMessageResp
from dcfs.errors import TechnicalError, FileSizeTooLarge

class TestDCMsgFileContentRepository:
    @pytest.fixture
    def mock_message_api(self, mocker):
        api = mocker.Mock(spec=MessageApi)
        api.discord_api = mocker.Mock()
        api.discord_api.bot = mocker.Mock()
        api.private_file_channel = 12345
        return api

    @pytest.mark.asyncio
    async def test_save_large_file_partitions(self, mock_message_api, mocker):
        # Setup: file twice the PART_SIZE
        data = b"a" * (PART_SIZE * 2)
        file_msg = FileMessageFromBuffer.new(buffer=data, name="large.txt")

        # Mock bot.send_file
        mock_message_api.discord_api.bot.send_file = AsyncMock(side_effect=[
            SendMessageResp(message_id=1),
            SendMessageResp(message_id=2)
        ])

        repo = DCMsgFileContentRepository(mock_message_api)

        # This SHOULD fail currently because partitioning is missing
        # Once fixed, it should return 2 SentFileMessage objects
        try:
            sent_messages = await repo.save(file_msg)

            assert len(sent_messages) == 2
            assert sent_messages[0].message_id == 1
            assert sent_messages[0].size == PART_SIZE
            assert sent_messages[1].message_id == 2
            assert sent_messages[1].size == PART_SIZE

            assert mock_message_api.discord_api.bot.send_file.call_count == 2
        except TechnicalError as e:
            if isinstance(e.__cause__, FileSizeTooLarge):
                pytest.fail("DCMsgFileContentRepository.save failed with FileSizeTooLarge, partitioning is likely missing or broken.")
            raise e
