import asyncio
import logging

from impacket.smbserver import SMBSERVER

from dcfs.config import Config
from dcfs.core import Clients

from .backend import DCFSSMBStorage

logger = logging.getLogger(__name__)

def create_smb_server(clients: Clients, config: Config) -> SMBSERVER:
    server = SMBSERVER((config.dcfs.smb.host, config.dcfs.smb.port))

    # Get current loop
    loop = asyncio.get_running_loop()

    # Add a share
    server.addShare("DCFS", "/", "Discord Cloud File System", DCFSSMBStorage(clients, loop))

    # Set up credentials if any
    if config.dcfs.users:
        for username, user_cfg in config.dcfs.users.items():
            server.add_user(username, "", user_cfg.password)

    server.setSMBChallenge('')
    return server

def run_smb_server(server: SMBSERVER):
    logger.info("Starting SMB server")
    server.serve()
