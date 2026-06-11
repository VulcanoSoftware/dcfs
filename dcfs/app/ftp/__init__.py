import logging

import aioftp
from dcfs.config import Config
from dcfs.core import Clients

from .path_io import DCFSPathIO

logger = logging.getLogger(__name__)


def create_ftp_server(clients: Clients, config: Config) -> aioftp.Server:
    users = []
    for username, user_cfg in config.dcfs.users.items():
        # aioftp uses User objects.
        # We can also handle permissions here.
        permissions = [
            aioftp.Permission("/", readable=True, writable=not user_cfg.readonly)
        ]
        users.append(aioftp.User(username, user_cfg.password, permissions=permissions))

    if not users:
        # Allow anonymous if no users configured?
        # The WebDAV app allows ReadonlyUser("anonymous")
        users.append(aioftp.User(permissions=[aioftp.Permission("/", readable=True, writable=False)]))

    class SessionPathIO(DCFSPathIO):
        def __init__(self, *args, **kwargs):
            super().__init__(clients, *args, **kwargs)

    server = aioftp.Server(users, path_io_factory=SessionPathIO)
    return server


async def run_ftp_server(server: aioftp.Server, host: str, port: int):
    logger.info(f"Starting FTP server on {host}:{port}")
    await server.run(host, port)
