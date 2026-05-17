import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Self, TypedDict

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DCFS_DATA_DIR", os.path.expanduser("~/.dcfs"))
CONFIG_FILE = os.environ.get("DCFS_CONFIG_FILE", "config.yaml")


@dataclass
class WebDAVConfig:
    host: str
    port: int
    path: str

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(host=data["host"], port=data["port"], path=data["path"])


@dataclass
class ManagerConfig:
    host: str
    port: int

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(host=data["host"], port=data["port"])


@dataclass
class DownloadConfig:
    chunk_size_kb: int

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(chunk_size_kb=data["chunk_size_kb"])


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
    """Optional at-rest encryption settings.

    ``passphrase_env`` / ``passphrase`` / ``passphrase_file`` are mutually
    exclusive; the loader picks the first one that is set. A file containing
    the passphrase is the recommended option for systemd deployments (pair
    it with a ``LoadCredential=`` unit directive).

    ``master_salt_file`` stores the 16-byte master salt produced on the
    very first run. Back this up alongside your TGFS metadata -- without it
    the master key cannot be re-derived even with the correct passphrase.
    """

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
        """Return the passphrase from whichever source is configured.

        Raises :class:`ValueError` if encryption is enabled but no source
        was configured. Stripping a trailing newline makes the
        ``passphrase_file`` flow forgiving of editors that always add one.
        """
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
class ServerConfig:
    host: str
    port: int

    @classmethod
    def from_dict(cls, data: Dict) -> "ServerConfig":
        return cls(host=data["host"], port=data["port"])


@dataclass
class TGFSConfig:
    users: dict[str, UserConfig]
    download: DownloadConfig
    jwt: JWTConfig
    metadata: Dict[str, MetadataConfig]
    server: ServerConfig
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
            encryption=EncryptionConfig.from_dict(data.get("encryption")),
        )


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.join(DATA_DIR, path)).replace("/", os.path.sep)


@dataclass
class DiscordConfig:
    """Configuration for the Discord storage backend.

    bot_tokens: one or more Discord bot tokens. Multiple tokens enable
                round-robin distribution (same pattern as the original
                multi-bot Telegram setup).
    private_file_channel: list of Discord channel IDs used as storage.
    max_file_size_mb: maximum size per attachment. Discord free tier allows
                      25 MB; Nitro / boosted servers allow up to 500 MB.
    """

    bot_tokens: List[str]
    private_file_channel: List[str]
    max_file_size_mb: int

    @classmethod
    def from_dict(cls, data: dict) -> "DiscordConfig":
        tokens = data.get("bot_tokens", [])
        if not tokens and "bot_token" in data:
            tokens = [data["bot_token"]]
        return cls(
            bot_tokens=tokens,
            private_file_channel=data["private_file_channel"]
            if isinstance(data["private_file_channel"], list)
            else [data["private_file_channel"]],
            max_file_size_mb=int(data.get("max_file_size_mb", 25)),
        )


@dataclass
class Config:
    discord: DiscordConfig
    tgfs: TGFSConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(
            discord=DiscordConfig.from_dict(data["discord"]),
            tgfs=TGFSConfig.from_dict(data["tgfs"]),
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
