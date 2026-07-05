import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Self, TypedDict

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DCFS_DATA_DIR", os.path.expanduser("~/.dcfs"))
CONFIG_FILE = os.environ.get("DCFS_CONFIG_FILE", "config.yaml")


@dataclass
class DownloadConfig:
    chunk_size_kb: int
    download_max_concurrent_parts: int = 3
    upload_max_retries: int = 10
    upload_retry_interval: int = 5
    upload_base_retry_delay: float = 2.0

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            chunk_size_kb=data["chunk_size_kb"],
            download_max_concurrent_parts=int(
                data.get("download_max_concurrent_parts", 3)
            ),
            upload_max_retries=int(data.get("upload_max_retries", 10)),
            upload_retry_interval=int(
                data.get("upload_retry_interval", 5)
            ),
            upload_base_retry_delay=float(
                data.get("upload_base_retry_delay", 2.0)
            ),
        )


@dataclass
class UserConfig:
    password: str
    readonly: bool

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(password=data["password"], readonly=data.get("readonly", False))


@dataclass
class JWTConfig:
    secret: str
    algorithm: str
    life: int

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            secret=data["secret"], algorithm=data["algorithm"], life=data["life"]
        )


@dataclass
class EncryptionConfig:
    """Optional at-rest encryption settings."""

    enabled: bool
    passphrase: Optional[str]
    passphrase_env: Optional[str]
    passphrase_file: Optional[str]
    master_salt_file: str
    chunk_size: int

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "EncryptionConfig":
        if not data:
            return cls(
                enabled=False,
                passphrase=None,
                passphrase_env=None,
                passphrase_file=None,
                master_salt_file=expand_path("master.salt"),
                chunk_size=64 * 1024,
            )
        return cls(
            enabled=bool(data.get("enabled", False)),
            passphrase=data.get("passphrase"),
            passphrase_env=data.get("passphrase_env"),
            passphrase_file=(
                expand_path(data["passphrase_file"])
                if data.get("passphrase_file")
                else None
            ),
            master_salt_file=expand_path(
                data.get("master_salt_file", "master.salt")
            ),
            chunk_size=int(data.get("chunk_size", 64 * 1024)),
        )

    def resolve_passphrase(self) -> str:
        if self.passphrase_env:
            value = os.environ.get(self.passphrase_env)
            if value is None:
                raise ValueError(
                    f"encryption passphrase env var '{self.passphrase_env}' not set"
                )
            return value
        if self.passphrase_file:
            with open(self.passphrase_file, "r", encoding="utf-8") as fh:
                return fh.read().rstrip("\n")
        if self.passphrase:
            return self.passphrase
        raise ValueError(
            "encryption enabled but no passphrase source configured "
            "(set one of passphrase, passphrase_env, passphrase_file)"
        )


@dataclass
class GithubRepoConfig:
    repo: str
    commit: str
    access_token: str

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            repo=data["repo"],
            commit=data["commit"],
            access_token=data["access_token"],
        )


class MetadataType(Enum):
    PINNED_MESSAGE = "pinned_message"
    GITHUB_REPO = "github_repo"


class MetadataConfigDict(TypedDict):
    name: str
    type: str
    github_repo: Optional[Dict]


@dataclass
class MetadataConfig:
    name: str
    type: MetadataType
    github_repo: Optional[GithubRepoConfig]

    @classmethod
    def from_dict(cls, data: MetadataConfigDict) -> Self:
        if (
            data.get("type", MetadataType.PINNED_MESSAGE.value)
            == MetadataType.PINNED_MESSAGE.value
        ):
            return cls(
                name=data.get("name", "default"),
                type=MetadataType.PINNED_MESSAGE,
                github_repo=None,
            )
        if data["type"] == MetadataType.GITHUB_REPO.value:
            if not (gh_repo_config := data.get("github_repo")):
                raise ValueError(
                    "GitHub repo configuration is required for GITHUB_REPO type"
                )
            return cls(
                name=data.get("name", "default"),
                type=MetadataType.GITHUB_REPO,
                github_repo=GithubRepoConfig.from_dict(gh_repo_config),
            )
        raise ValueError(
            f"Unknown metadata type: {data['type']}, available options: {', '.join(e.value for e in MetadataType)}"
        )


@dataclass
class FTPConfig:
    enabled: bool
    host: str
    port: int

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "FTPConfig":
        if not data:
            return cls(enabled=False, host="127.0.0.1", port=2121)
        return cls(
            enabled=bool(data.get("enabled", False)),
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 2121)),
        )


@dataclass
class SFTPConfig:
    enabled: bool
    host: str
    port: int

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "SFTPConfig":
        if not data:
            return cls(enabled=False, host="127.0.0.1", port=2022)
        return cls(
            enabled=bool(data.get("enabled", False)),
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 2022)),
        )


@dataclass
class SMBConfig:
    enabled: bool
    host: str
    port: int

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "SMBConfig":
        if not data:
            return cls(enabled=False, host="127.0.0.1", port=4445)
        return cls(
            enabled=bool(data.get("enabled", False)),
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 4445)),
        )


@dataclass
class ServerConfig:
    host: str
    port: int

    @classmethod
    def from_dict(cls, data: Dict) -> "ServerConfig":
        return cls(host=data["host"], port=data["port"])


@dataclass
class DCFSConfig:
    users: dict[str, UserConfig]
    download: DownloadConfig
    jwt: JWTConfig
    metadata: Dict[str, MetadataConfig]
    server: ServerConfig
    ftp: FTPConfig
    sftp: SFTPConfig
    smb: SMBConfig
    encryption: EncryptionConfig

    @classmethod
    def from_dict(cls, data: Dict) -> Self:
        metadata_config: Dict[str, MetadataConfigDict] = data.get("metadata", {})

        return cls(
            users=(
                {
                    username: UserConfig.from_dict(user)
                    for username, user in data["users"].items()
                }
                if data["users"]
                else {}
            ),
            download=DownloadConfig.from_dict(data["download"]),
            jwt=JWTConfig.from_dict(data["jwt"]),
            metadata={
                k: MetadataConfig.from_dict(v) for k, v in metadata_config.items()
            },
            server=ServerConfig.from_dict(data["server"]),
            ftp=FTPConfig.from_dict(data.get("ftp")),
            sftp=SFTPConfig.from_dict(data.get("sftp")),
            smb=SMBConfig.from_dict(data.get("smb")),
            encryption=EncryptionConfig.from_dict(data.get("encryption")),
        )


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.join(DATA_DIR, path)).replace("/", os.path.sep)


@dataclass
class DiscordConfig:
    bot_token: str
    guild_id: int
    private_file_channel: List[str]
    delete_messages_on_remove: bool
    max_file_size_bytes: int

    @classmethod
    def from_dict(cls, data: dict) -> "DiscordConfig":
        return cls(
            bot_token=data["bot_token"],
            guild_id=int(data["guild_id"]) if data.get("guild_id") else 0,
            private_file_channel=data["private_file_channel"],
            delete_messages_on_remove=bool(
                data.get("delete_messages_on_remove", False)
            ),
            max_file_size_bytes=int(data.get("max_file_size_bytes", 8_000_000)),
        )


@dataclass
class Config:
    discord: DiscordConfig
    dcfs: DCFSConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(
            discord=DiscordConfig.from_dict(data["discord"]),
            dcfs=DCFSConfig.from_dict(data["dcfs"]),
        )


__config_file_path = expand_path(os.path.join(DATA_DIR, CONFIG_FILE))
__config: Config | None = None


def _load_config(file_path: str) -> Config:
    with open(file_path, "r") as file:
        data = yaml.safe_load(file)
        return Config.from_dict(data)


def get_config() -> Config:
    global __config
    if __config is None:
        logger.info(f"Using configuration file: {__config_file_path}")
        __config = _load_config(__config_file_path)
    return __config
