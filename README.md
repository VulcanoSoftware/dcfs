# DCFS — Discord Cloud File System

DCFS is a WebDAV server that uses **Discord channels as a storage backend**.
It is a drop-in replacement for [tgfs](https://github.com/WheatCarrier/tgfs),
with the Telegram backend swapped out for Discord while keeping everything
else — WebDAV interface, encryption, metadata storage, authentication — exactly
the same.

## How it works

| tgfs (original) | dcfs (this project) |
|---|---|
| Telegram MTProto client (telethon / pyrogram) | Discord REST API (aiohttp) |
| Telegram channel as storage | Discord channel as storage |
| Bot token(s) + optional user account | Discord bot token(s) |
| Pinned messages for metadata | Discord pinned messages |
| File parts via SaveBigFilePart / SaveFilePart | Multipart uploads as Discord attachments |
| 2 GB / 4 GB file parts (Premium) | 25 MB per attachment (free) / up to 500 MB (Nitro) |

Files larger than `max_file_size_mb` are automatically split into multiple
Discord messages, each carrying one attachment part, and reassembled on
download — exactly as tgfs did for large files.

## Setup

### 1. Create a Discord bot

1. Go to <https://discord.com/developers/applications> and create a new application.
2. Under **Bot**, click **Add Bot**.
3. Enable **Message Content Intent** and **Server Members Intent** under
   Privileged Gateway Intents.
4. Copy the bot token.
5. Invite the bot to your server with at minimum the following permissions:
   - Read Messages / View Channels
   - Send Messages
   - Manage Messages (needed for pinning)
   - Attach Files
   - Read Message History

### 2. Get the storage channel ID

Enable **Developer Mode** in Discord settings (Settings → Advanced → Developer
Mode), then right-click your storage channel and select **Copy Channel ID**.

### 3. Configure

Copy `demo-config.yaml` to `~/.dcfs/config.yaml` (or set `DCFS_CONFIG_FILE`):

```yaml
discord:
  bot_tokens:
    - "YOUR_DISCORD_BOT_TOKEN"
  private_file_channel:
    - "YOUR_CHANNEL_ID"
  max_file_size_mb: 25   # 25 for free, 50/100/500 for boosted servers

tgfs:
  users:
    admin:
      password: changeme
  download:
    chunk_size_kb: 1024
  jwt:
    secret: change-this-secret
    algorithm: HS256
    life: 604800
  metadata:
    "YOUR_CHANNEL_ID":
      name: default
      type: pinned_message
  server:
    host: 0.0.0.0
    port: 1900
```

### 4. Run

```bash
pip install poetry
poetry install
python main.py
```

### 5. Mount via WebDAV

| Client | URL |
|---|---|
| macOS Finder | `http://localhost:1900` |
| Windows | Map network drive → `http://localhost:1900` |
| Linux (davfs2) | `mount -t davfs http://localhost:1900 /mnt/dcfs` |

## Multiple bots

Like tgfs, you can provide multiple bot tokens under `bot_tokens` to spread
upload/download traffic across bots:

```yaml
discord:
  bot_tokens:
    - "TOKEN_BOT_1"
    - "TOKEN_BOT_2"
    - "TOKEN_BOT_3"
```

## Encryption

At-rest encryption is identical to tgfs: AES-256-GCM with per-chunk
authentication, keyed from a user-supplied passphrase via Argon2. Enable it
in the config:

```yaml
tgfs:
  encryption:
    enabled: true
    passphrase_env: DCFS_MASTER_PASSPHRASE
    master_salt_file: master.salt
    chunk_size: 65536
```

## Differences from tgfs

- **No Telegram account needed** — only Discord bot token(s).
- **Smaller per-message file size** — Discord's free tier caps attachments at
  25 MB. Boosted servers raise this limit. Large files are chunked automatically.
- **No pyrogram / telethon dependency** — replaced with `aiohttp`.
- **Message search** — uses Discord channel history scan instead of Telegram's
  built-in search API.
- **`edit_message_media`** — Discord does not support replacing an attachment
  in-place; DCFS deletes the old message and sends a new one, then updates
  the stored message ID.

## License

Same as tgfs — see `LICENSE`.
