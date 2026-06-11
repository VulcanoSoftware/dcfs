import logging
import os

import asyncssh

from dcfs.config import DATA_DIR, Config
from dcfs.core import Clients

from .handler import DCFSSFTPHandler

logger = logging.getLogger(__name__)

class DCFSSFTPServer(asyncssh.SSHServer):
    def __init__(self, clients: Clients, config: Config):
        self.clients = clients
        self.config = config

    def session_requested(self):
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        if username in self.config.dcfs.users:
            if self.config.dcfs.users[username].password == password:
                return True
        return False

async def create_sftp_server(clients: Clients, config: Config):
    # Persistent host key
    host_key_path = os.path.join(DATA_DIR, "host.key")
    if os.path.exists(host_key_path):
        try:
            host_key = asyncssh.read_private_key(host_key_path)
            logger.info(f"Loaded persistent SFTP host key from {host_key_path}")
        except Exception as e:
            logger.warning(f"Failed to read SFTP host key from {host_key_path}: {e}. Generating a new one.")
            host_key = asyncssh.generate_private_key('ssh-rsa')
            host_key.write_private_key(host_key_path)
    else:
        logger.info(f"Generating new persistent SFTP host key at {host_key_path}")
        host_key = asyncssh.generate_private_key('ssh-rsa')
        try:
             os.makedirs(DATA_DIR, exist_ok=True)
             host_key.write_private_key(host_key_path)
        except Exception as e:
             logger.warning(f"Failed to save SFTP host key to {host_key_path}: {e}")

    def server_factory():
        return DCFSSFTPServer(clients, config)

    def sftp_factory(conn):
        return DCFSSFTPHandler(clients, conn)

    return await asyncssh.create_server(
        server_factory,
        config.dcfs.sftp.host,
        config.dcfs.sftp.port,
        server_host_keys=[host_key],
        sftp_factory=sftp_factory
    )

async def run_sftp_server(server: asyncssh.SSHListener, host: str, port: int):
    logger.info(f"Starting SFTP server on {host}:{port}")
    await server.wait_closed()
