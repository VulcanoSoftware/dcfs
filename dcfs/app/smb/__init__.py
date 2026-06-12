import asyncio
import logging
import os

from impacket import ntlm
from impacket.smbserver import SimpleSMBServer

from dcfs.config import Config
from dcfs.core import Clients

from .backend import DCFSSMBStorage

logger = logging.getLogger(__name__)

def create_smb_server(clients: Clients, config: Config) -> SimpleSMBServer:
    server = SimpleSMBServer(listenAddress=config.dcfs.smb.host, listenPort=config.dcfs.smb.port)

    # Create a safe directory for the SMB share to avoid sharing the root filesystem
    share_path = os.path.join(os.getcwd(), ".smb_share")
    os.makedirs(share_path, exist_ok=True)

    # Add a README to the share to explain its current status
    readme_path = os.path.join(share_path, "README.txt")
    if not os.path.exists(readme_path):
        with open(readme_path, "w") as f:
            f.write("Welcome to DCFS SMB share.\n")
            f.write("Currently, the SMB server provides access to this local directory.\n")
            f.write("Full integration with the Discord backend is under development.\n")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    # Add a share
    # shareType='0' for DISK_SHARE
    # readOnly='no'
    server.addShare("DCFS", share_path, "Discord Cloud File System", "0", "no")

    # Store the custom storage backend for future use when VFS support is implemented
    setattr(server, "dcfs_storage", DCFSSMBStorage(clients, loop))

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
