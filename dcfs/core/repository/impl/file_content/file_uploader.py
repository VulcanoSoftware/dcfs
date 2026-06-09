import io
import logging
import os

from dcfs.config import get_config
from dcfs.discord.interface import IDiscordClient
from dcfs.errors import FileSizeTooLarge, TechnicalError
from dcfs.reqres import (
    SendFileReq,
    SendMessageResp,
    UploadableFileMessage,
)

logger = logging.getLogger(__name__)

DEFAULT_DISCORD_MAX_FILE_SIZE = 8_000_000


def discord_max_file_size_bytes() -> int:
    if (raw := os.environ.get("DCFS_DISCORD_MAX_FILE_SIZE_BYTES")):
        try:
            value = int(raw)
            if value > 0:
                return value
        except Exception:
            pass
    try:
        config = get_config()
        value = int(getattr(config.discord, "max_file_size_bytes", 0) or 0)
        if value > 0:
            return value
    except Exception:
        pass
    return DEFAULT_DISCORD_MAX_FILE_SIZE


class FileUploader:
    def __init__(
        self,
        client: IDiscordClient,
        file_msg: UploadableFileMessage,
    ):
        self.client = client
        self._file_msg = file_msg
        self._file_name = self._file_msg.file_name()

        # For Discord, we upload the entire file as one attachment
        self._buffer = io.BytesIO()

    async def _close(self) -> None:
        await self._file_msg.close()

    async def _cancelled(self) -> bool:
        if tt := self._file_msg.task_tracker:
            return await tt.cancelled()
        return False

    async def upload(self) -> int:
        """Read the entire file content, checking against Discord's size limit."""
        if await self._cancelled():
            logger.warning(f"Upload cancelled for {self._file_name}")
            return 0

        limit = discord_max_file_size_bytes()
        await self._file_msg.open()
        self._buffer = io.BytesIO()
        while True:
            chunk = await self._file_msg.read(1024 * 1024)
            if not chunk:
                break
            self._buffer.write(chunk)
            if self._buffer.tell() > limit:
                raise FileSizeTooLarge(self._buffer.tell())
            if await self._cancelled():
                logger.warning(f"Upload cancelled for {self._file_name}")
                return 0

        size = self._buffer.tell()
        self._buffer.seek(0)
        return size

    def reset_buffer(self) -> None:
        """Seek the upload buffer back to the start for a retry."""
        self._buffer.seek(0)

    async def send(self, chat_id: int, caption: str = "") -> SendMessageResp:
        """Send the uploaded file as a Discord message attachment."""
        logger.debug(f"Sending file {self._file_name} to chat {chat_id}")

        content = self._buffer.read()
        if not content:
            raise TechnicalError(f"No content to send for {self._file_name}")

        logger.info(
            f"Sending {len(content)} bytes as '{self._file_name}' to chat {chat_id}"
        )

        req = SendFileReq(
            chat=chat_id,
            name=self._file_name,
            caption=caption,
            buffer=content,
        )

        return await self.client.send_file(req)
