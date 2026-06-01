from typing import Dict, Optional

from dcfs.config import EncryptionConfig, MetadataConfig, MetadataType
from dcfs.core.api import DirectoryApi, FileApi, FileDescApi, MessageApi, MetaDataApi
from dcfs.core.repository.impl import (
    DCMsgFDRepository,
    DCMsgFileContentRepository,
    DCMsgMetadataRepository,
)
from dcfs.core.repository.interface import (
    IFileContentRepository,
    IMetaDataRepository,
)
from dcfs.discord import DiscordApi


class Client:
    def __init__(
        self,
        name: str,
        message_api: MessageApi,
        file_api: FileApi,
        dir_api: DirectoryApi,
        fc_repo: IFileContentRepository,
    ):
        self.name = name
        self.message_api = message_api
        self.file_api = file_api
        self.dir_api = dir_api
        self.fc_repo = fc_repo

    @classmethod
    async def create(
        cls,
        channel_id: str,
        metadata_cfg: MetadataConfig,
        discord_api: DiscordApi,
        encryption_cfg: Optional[EncryptionConfig] = None,
    ) -> "Client":
        channel = await discord_api.next_bot.resolve_channel_id(channel_id)
        message_api = MessageApi(discord_api, channel)

        fc_repo: IFileContentRepository = DCMsgFileContentRepository(
            message_api,
        )

        # Wrap the file-content repository in an encryption decorator if
        # encryption is enabled in the config. Everything downstream
        # (FileApi, WebDAV, etc.) is unchanged: the wrapper preserves the
        # IFileContentRepository contract.
        if encryption_cfg is not None and encryption_cfg.enabled:
            from dcfs.crypto.bootstrap import load_master_key
            from dcfs.crypto.repository import EncryptingFileContentRepository

            master = load_master_key(encryption_cfg)
            fc_repo = EncryptingFileContentRepository(
                fc_repo,
                master_key=master.key,
                chunk_size=encryption_cfg.chunk_size,
            )

        fd_repo = DCMsgFDRepository(message_api)

        if metadata_cfg.type == MetadataType.PINNED_MESSAGE:
            metadata_repo: IMetaDataRepository = DCMsgMetadataRepository(
                message_api, fc_repo
            )
        else:
            if (github_repo_config := metadata_cfg.github_repo) is None:
                raise ValueError(
                    "configuration dcfs -> metadata -> github is required."
                )
            from dcfs.core.repository.impl.metadata.github_repo import (
                GithubRepoMetadataRepository,
            )

            metadata_repo = GithubRepoMetadataRepository(github_repo_config)

        fd_api = FileDescApi(fd_repo, fc_repo)

        metadata_api = MetaDataApi(metadata_repo)
        await metadata_api.init()

        file_api = FileApi(metadata_api, fd_api, message_api)
        dir_api = DirectoryApi(metadata_api, file_api, message_api)

        return cls(
            name=metadata_cfg.name,
            message_api=message_api,
            file_api=file_api,
            dir_api=dir_api,
            fc_repo=fc_repo,
        )


Clients = Dict[str, Client]
