import asyncio
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

from uvicorn.config import Config as UvicornConfig
from uvicorn.server import Server

from dcfs.app import create_app
from dcfs.app.ftp import create_ftp_server, run_ftp_server
from dcfs.config import Config, get_config
from dcfs.core import Client, Clients
from dcfs.discord import DiscordApi
from dcfs.discord.impl.discord_bot import DiscordBotAPI, login_as_bots


async def create_clients(config: Config) -> Clients:
    discord_bots = await login_as_bots(config)
    discord_api = DiscordApi(
        bots=[DiscordBotAPI(bot, config.discord.bot_token) for bot in discord_bots],
    )

    clients: Clients = {}

    for channel_id in config.discord.private_file_channel:
        metadata_cfg = config.dcfs.metadata[channel_id]
        clients[metadata_cfg.name] = await Client.create(
            channel_id,
            metadata_cfg,
            discord_api,
            encryption_cfg=config.dcfs.encryption,
            download_max_concurrent_parts=config.dcfs.download.download_max_concurrent_parts,
        )
    return clients


async def run_server(app, host: str, port: int, name: str):
    """Run a server with proper configuration"""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {name} server on {host}:{port}")

    server_config = UvicornConfig(
        app,
        host=host,
        port=port,
        loop="none",
        log_level="info",
    )
    server = Server(config=server_config)
    await server.serve()


async def main():
    config = get_config()

    clients = await create_clients(config)

    tasks = []

    app = create_app(clients, config)
    tasks.append(
        run_server(app, config.dcfs.server.host, config.dcfs.server.port, "DCFS")
    )

    if config.dcfs.ftp.enabled:
        ftp_server = create_ftp_server(clients, config)
        tasks.append(
            run_ftp_server(ftp_server, config.dcfs.ftp.host, config.dcfs.ftp.port)
        )

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        import uvloop  # type: ignore[import]

        uvloop.run(main())
    except ImportError:
        logging.warning("uvloop is not installed, using default event loop")
        asyncio.run(main())
