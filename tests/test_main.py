import pytest

from main import create_clients, main, run_server


class TestMain:
    @pytest.mark.asyncio
    async def test_create_clients(self, mocker):
        # Setup mocks
        mock_login_bots = mocker.AsyncMock()
        mock_client_create = mocker.AsyncMock()
        mock_discord_api_class = mocker.patch("main.DiscordApi")
        mock_discord_bot_api_class = mocker.patch("main.DiscordBotAPI")

        mocker.patch("main.login_as_bots", mock_login_bots)
        mocker.patch("main.Client.create", mock_client_create)

        mock_config = mocker.Mock()
        mock_config.discord.bot_token = "test_token"
        mock_config.discord.private_file_channel = ["12345"]

        mock_metadata_cfg = mocker.Mock()
        mock_metadata_cfg.name = "test_client"
        mock_config.dcfs.metadata = {"12345": mock_metadata_cfg}

        mock_bot = mocker.Mock()
        mock_bot_instance = mocker.Mock()
        mock_discord_api = mocker.Mock()
        mock_client = mocker.Mock()

        mock_login_bots.return_value = [mock_bot]
        mock_discord_bot_api_class.return_value = mock_bot_instance
        mock_discord_api_class.return_value = mock_discord_api
        mock_client_create.return_value = mock_client

        # Call function
        result = await create_clients(mock_config)

        # Assertions
        mock_login_bots.assert_called_once_with(mock_config)
        mock_discord_bot_api_class.assert_called_once_with(mock_bot, "test_token")
        mock_discord_api_class.assert_called_once_with(
            bots=[mock_bot_instance],
        )
        mock_client_create.assert_called_once_with(
            "12345",
            mock_metadata_cfg,
            mock_discord_api,
            encryption_cfg=mock_config.dcfs.encryption,
            download_max_concurrent_parts=mock_config.dcfs.download.download_max_concurrent_parts,
        )
        assert result == {"test_client": mock_client}

    @pytest.mark.asyncio
    async def test_create_clients_multiple_channels(self, mocker):
        # Setup mocks
        mock_login_bots = mocker.AsyncMock()
        mock_client_create = mocker.AsyncMock()
        mocker.patch("main.login_as_bots", mock_login_bots)
        mocker.patch("main.Client.create", mock_client_create)
        mocker.patch("main.DiscordApi")
        mocker.patch("main.DiscordBotAPI")

        mock_config = mocker.Mock()
        mock_config.discord.bot_token = "test_token"
        mock_config.discord.private_file_channel = ["12345", "67890"]

        mock_metadata_cfg_1 = mocker.Mock()
        mock_metadata_cfg_1.name = "client_a"
        mock_metadata_cfg_2 = mocker.Mock()
        mock_metadata_cfg_2.name = "client_b"
        mock_config.dcfs.metadata = {
            "12345": mock_metadata_cfg_1,
            "67890": mock_metadata_cfg_2,
        }

        mock_login_bots.return_value = [mocker.Mock()]
        mock_client_create.side_effect = [mocker.Mock(), mocker.Mock()]

        # Call function
        result = await create_clients(mock_config)

        # Assertions
        assert mock_client_create.call_count == 2
        assert len(result) == 2
        assert "client_a" in result
        assert "client_b" in result

    @pytest.mark.asyncio
    async def test_run_server(self, mocker):
        # Setup mocks
        mock_get_logger = mocker.patch("main.logging.getLogger")
        mock_uvicorn_config = mocker.patch("main.UvicornConfig")
        mock_server_class = mocker.patch("main.Server")
        mock_app = mocker.Mock()
        mock_logger = mocker.Mock()
        mock_config = mocker.Mock()
        mock_server = mocker.Mock()
        mock_server.serve = mocker.AsyncMock()

        mock_get_logger.return_value = mock_logger
        mock_uvicorn_config.return_value = mock_config
        mock_server_class.return_value = mock_server

        # Call function
        await run_server(mock_app, "localhost", 8080, "DCFS")

        # Assertions
        mock_logger.info.assert_called_once_with(
            "Starting DCFS server on localhost:8080"
        )
        mock_uvicorn_config.assert_called_once_with(
            mock_app,
            host="localhost",
            port=8080,
            loop="none",
            log_level="info",
        )
        mock_server_class.assert_called_once_with(config=mock_config)
        mock_server.serve.assert_called_once()

    @pytest.mark.asyncio
    async def test_main(self, mocker):
        # Setup mocks
        mock_get_config = mocker.patch("main.get_config")
        mock_create_clients = mocker.patch("main.create_clients")
        mock_create_app = mocker.patch("main.create_app")
        mock_run_server = mocker.patch("main.run_server")
        mock_config = mocker.Mock()
        mock_config.dcfs.server.host = "0.0.0.0"
        mock_config.dcfs.server.port = 9000
        mock_config.dcfs.ftp.enabled = False

        mock_clients = mocker.Mock()
        mock_app = mocker.Mock()

        mock_get_config.return_value = mock_config
        mock_create_clients.return_value = mock_clients
        mock_create_app.return_value = mock_app
        mock_run_server.return_value = None

        # Call function
        await main()

        # Assertions
        mock_get_config.assert_called_once()
        mock_create_clients.assert_called_once_with(mock_config)
        mock_create_app.assert_called_once_with(mock_clients, mock_config)
        mock_run_server.assert_called_once_with(mock_app, "0.0.0.0", 9000, "DCFS")
