import asyncio
import logging

from impacket.smbserver import SimpleSMBServer
from impacket import ntlm

from dcfs.config import Config
from dcfs.core import Clients

from .backend import DCFSSMBStorage

logger = logging.getLogger(__name__)

def create_smb_server(clients: Clients, config: Config) -> SimpleSMBServer:
    server = SimpleSMBServer(listenAddress=config.dcfs.smb.host, listenPort=config.dcfs.smb.port)

    # Get current loop
    loop = asyncio.get_running_loop()

    # Add a share
    # shareType='0' for DISK_SHARE
    # readOnly='no'
    server.addShare("DCFS", "/", "Discord Cloud File System", "0", "no", DCFSSMBStorage(clients, loop))

    # Set up credentials if any
    if config.dcfs.users:
        for username, user_cfg in config.dcfs.users.items():
            # Calculate NTLM hashes for addCredential
            lmhash = ntlm.compute_lmhash(user_cfg.password)
            nthash = ntlm.compute_nthash(user_cfg.password)
            # domain='0' (default)
            server.addCredential(username, "0", lmhash, nthash)

    server.setSMBChallenge('')
    return server

def run_smb_server(server: SimpleSMBServer):
    logger.info("Starting SMB server")
    server.start()
