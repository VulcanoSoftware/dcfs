import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio


class TestCreateClients:
    @pytest.fixture
    def mock_config(self, mocker):
        config = mocker.Mock()
        config.discord = mocker.Mock()
        config.discord.bot_tokens = ["token1", "token2"]
        config.discord.private_file_channel = ["123456789"]
        config.tgfs = mocker.Mock()
        config.tgfs.metadata = {
            "123456789": mocker.Mock(name="default")
        }
        config.tgfs.encryption = None
        return config

    async def test_create_clients_discord(self, mock_config, mocker):
        mock_login = mocker.patch("main.login", new_callable=AsyncMock)
        mock_discord_bot = mocker.Mock()
        mock_login.return_value = [mock_discord_bot]

        mock_tdlib = mocker.patch("main.TDLibApi")
        mock_client_create = mocker.patch("main.Client.create", new_callable=AsyncMock)

        from main import create_clients
        await create_clients(mock_config)

        mock_login.assert_called_once_with(mock_config)
        mock_client_create.assert_called_once()
