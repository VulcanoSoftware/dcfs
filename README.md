<p align="center">
  <h1 align="center">dcfs</h1>
</p>

[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?style=for-the-badge&logo=docker&logoColor=white)](https://github.com/VulcanoSoftware/dcfs/pkgs/container/dcfs)
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Live-blue?style=for-the-badge&logo=github)](https://vulcanosoftware.github.io/dcfs)

# dcfs

Discord becomes a WebDAV server. This project originally started as a fork of [tgfs](https://github.com/TheodoreKrypton/tgfs), but has since diverged into an independent codebase with its own behavior and configuration.

## Features
* Upload and download files to/from a private Discord channel via WebDAV
* Group files on Discord channels into folders
* Infinite versioning of files and folders (Folder versioning is only available when Metadata is maintained on Github repository)
* File size is unlimited (larger files are chunked into parts but appear as a single file to the user)
* Live streaming of videos
* **Optional at-rest encryption** (AES-256-GCM, see below)

## Tested Clients
* [rclone](https://rclone.org/)
* [Cyberduck](https://cyberduck.io/)
* [WinSCP](https://winscp.net/)
* [Documents](https://readdle.com/documents) by Readdle
* [VidHub](https://okaapps.com/product/1659622164)

## Configuration

Create a `config.yaml` file:

```yaml
discord:
  bot_token: YOUR_BOT_TOKEN
  guild_id: YOUR_GUILD_ID
  private_file_channel:
    - CHANNEL_ID_1
  delete_messages_on_remove: false
dcfs:
  users:
    user:
      password: password
      readonly: false
  download:
    chunk_size_kb: 1024
    download_max_concurrent_parts: 3
  jwt:
    secret: your-secret-key
    algorithm: HS256
    life: 604800
  metadata:
    CHANNEL_ID_1:
      name: default
      type: pinned_message
  server:
    host: 0.0.0.0
    port: 1900
  encryption:
    enabled: false
```

### Setting up a Discord Bot

1. Go to https://discord.com/developers/applications and create a new application
2. Go to the Bot section and create a bot
3. Enable the following Privileged Gateway Intents:
   - Message Content Intent
   - Server Members Intent (if needed)
4. Invite the bot to your server with permissions:
   - Send Messages
   - Manage Messages
   - Read Message History
   - Attach Files
   - Pin Messages

## At-rest encryption

When ``encryption.enabled: true`` is set in ``config.yaml``, every byte
DCFS uploads to Discord is encrypted client-side. The Discord channel and
the metadata repository never see plaintext.

* **Cipher:** AES-256-GCM in 64 KiB chunks, each with its own nonce + auth tag.
  Random-access decryption (HTTP Range requests, video streaming) keeps working.
* **Keys:** the master key is derived from a passphrase via Argon2id at startup.
  Per-file keys are derived via HKDF-SHA256 from the master key and a 32-byte
  random salt stored in the file header.
* **Header:** each encrypted file starts with a self-describing 60-byte header
  embedded *inline* in the first Discord message, so a file can be decrypted
  from the channel even if the DCFS metadata store is lost.
* **Tamper detection:** every chunk has its own GCM tag plus an HMAC on the
  header, so flipped bits or chunk reordering are caught before plaintext is
  returned.

Set up:

```yaml
dcfs:
  encryption:
    enabled: true
    passphrase_env: DCFS_MASTER_PASSPHRASE
    master_salt_file: master.salt
    chunk_size: 65536
```

## Development

Install the dependencies:
```bash
poetry install
```

Run the app:
```bash
poetry run python main.py
```

## Docker

The Docker image is published to GitHub Container Registry:

```bash
docker run --pull=always -it -p 1900:1900 -v /path/to/.dcfs:/home/dcfs/.dcfs ghcr.io/vulcanosoftware/dcfs:latest
```

Put your `config.yaml` in the mounted `.dcfs` directory (`/path/to/.dcfs/config.yaml`).

Typecheck && lint:
```bash
make mypy
make ruff
```

Before committing and pushing, run the following command to install git hooks:
```bash
pre-commit install
```

## Web Frontend

A Next.js-based web frontend is available at the [GitHub Pages site](https://vulcanosoftware.github.io/dcfs) with the following features:

* **Config Generator** — Interactive form to generate `config.yaml` files with validation
* **Getting Started Guide** — Step-by-step wizard for setting up your Discord bot, channels, and server
* **WebDAV App** — Built-in file explorer to browse, upload, download, and manage files via WebDAV (optionally shows background tasks when the manager API is available)

The frontend source code is in the `dcfs-gh-pages/` directory.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
