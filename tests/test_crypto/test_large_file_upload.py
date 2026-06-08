"""Integration test: large-file upload through the encryption + partitioning
pipeline reproduces (and now passes) the exact scenario that caused
``FileSizeTooLarge`` in production.

The test mirrors the real code path:

    EncryptingFileContentRepository.save()
      → wraps plaintext in EncryptingFileMessage
      → DCMsgFileContentRepository.save()  (simulated by _InMemoryPartRepo)
        → partitions into 7 MB parts (PART_SIZE)
        → FileUploader.upload()  (simulated by _read_all)
          → reads 1 MB at a time from EncryptingFileMessage.read()

Before the fix, the EncryptingFileMessage ignored the partition size set by
DCMsgFileContentRepository, so the first part would accumulate ~27 MB and
trigger FileSizeTooLarge (>25 MB).  After the fix, each part stays within
its declared size.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass

import pytest

from dcfs.core.model import DCFSFileVersion
from dcfs.core.repository.impl.file_content import PART_SIZE
from dcfs.core.repository.impl.file_content.file_uploader import (
    DISCORD_MAX_FILE_SIZE,
)
from dcfs.core.repository.interface import IFileContentRepository
from dcfs.crypto.cipher import CHUNK_OVERHEAD
from dcfs.crypto.header import HEADER_SIZE
from dcfs.crypto.repository import EncryptingFileContentRepository
from dcfs.crypto.stream import EncryptingFileMessage
from dcfs.reqres import (
    FileContent,
    FileMessageFromBuffer,
    SentFileMessage,
    UploadableFileMessage,
)

# ---------------------------------------------------------------------------
# Minimal in-memory backend that records per-part ciphertext sizes
# ---------------------------------------------------------------------------


@dataclass
class _FakeFileVersion(DCFSFileVersion):
    pass


class _RecordingInMemoryRepo(IFileContentRepository):
    """Simulates DCMsgFileContentRepository.save() with partitioning + FileUploader."""

    def __init__(self) -> None:
        self._files: dict[int, bytes] = {}
        self._next_msg_id = 1000
        self.part_sizes_observed: list[int] = []

    async def _upload_part(
        self, file_msg: UploadableFileMessage
    ) -> SentFileMessage:
        """Simulate FileUploader.upload(): read 1 MB at a time, enforce limit."""
        buf = bytearray()
        while True:
            chunk = await file_msg.read(1024 * 1024)
            if not chunk:
                break
            buf += chunk
            if len(buf) > DISCORD_MAX_FILE_SIZE:
                from dcfs.errors import FileSizeTooLarge

                raise FileSizeTooLarge(len(buf))

        part_bytes = bytes(buf)
        self.part_sizes_observed.append(len(part_bytes))

        msg_id = self._next_msg_id
        self._next_msg_id += 1
        self._files[msg_id] = part_bytes
        return SentFileMessage(message_id=msg_id, size=len(part_bytes))

    @staticmethod
    def _partition(size: int, part_size: int):
        parts = (size + part_size - 1) // part_size
        for i in range(parts - 1):
            yield part_size
        yield size - (parts - 1) * part_size

    async def save(
        self, file_msg: UploadableFileMessage
    ) -> list[SentFileMessage]:
        """Mirror DCMsgFileContentRepository.save(): partition + upload each part."""
        size = file_msg.get_size()
        res: list[SentFileMessage] = []
        file_name = file_msg.name or "unnamed"

        for i, part_size in enumerate(self._partition(size, PART_SIZE)):
            file_msg.name = f"[part{i+1}]{file_name}"
            file_msg.size = part_size
            res.append(await self._upload_part(file_msg))
            file_msg.next_part(part_size)
        return res

    async def get(self, fv, begin: int, end: int, name: str) -> FileContent:
        parts: list[bytes] = []
        for msg_id in fv.message_ids:
            parts.append(self._files[msg_id])
        ciphertext = b"".join(parts)
        if end < 0:
            end = len(ciphertext) - 1

        async def stream():
            i = begin
            for step in (3, 17, 1024, 8192):
                if i > end:
                    break
                yield ciphertext[i : min(i + step, end + 1)]
                i += step
            if i <= end:
                yield ciphertext[i : end + 1]

        return stream()

    async def update(self, message_id: int, buffer: bytes, name: str) -> int:
        self._files[message_id] = buffer
        return message_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

MASTER_KEY = b"\x77" * 32
CHUNK_SIZE = 64 * 1024  # 64 KiB – matches production default


async def _collect(stream) -> bytes:
    buf = bytearray()
    async for piece in stream:
        buf += piece
    return bytes(buf)


@pytest.mark.parametrize(
    "plaintext_size",
    [
        25 * 1024 * 1024,     # 25 MB – just at Discord limit
        50 * 1024 * 1024,     # 50 MB – 3 parts
        100 * 1024 * 1024,    # 100 MB – the exact scenario from the bug report
    ],
    ids=["25MB", "50MB", "100MB"],
)
async def test_large_file_parts_stay_under_discord_limit(plaintext_size: int):
    """Each part emitted by the encryption + partition pipeline must be <= 25 MB.

    This is the exact scenario that caused ``FileSizeTooLarge: File size 27262976
    exceeds Discord's limit`` when uploading a 100 MB file via WebDAV PUT.
    """
    inner = _RecordingInMemoryRepo()
    repo = EncryptingFileContentRepository(
        inner, master_key=MASTER_KEY, chunk_size=CHUNK_SIZE
    )

    # Generate random plaintext of the requested size.
    plaintext = os.urandom(plaintext_size)
    file_msg = FileMessageFromBuffer.new(buffer=plaintext, name="big.bin")

    # save() goes through EncryptingFileContentRepository → wraps in
    # EncryptingFileMessage → inner DCMsgFileContentRepository.save()
    # (simulated by _RecordingInMemoryRepo).
    sent = await repo.save(file_msg)

    # Verify all parts are under the Discord limit.
    for i, part_size in enumerate(inner.part_sizes_observed):
        assert part_size <= DISCORD_MAX_FILE_SIZE, (
            f"Part {i+1} is {part_size} bytes "
            f"(>{DISCORD_MAX_FILE_SIZE} Discord limit)"
        )

    # Verify total ciphertext size matches.
    total_ciphertext = sum(s.size for s in sent)
    assert total_ciphertext == sum(inner.part_sizes_observed)

    # Verify round-trip decryption.
    fv = _FakeFileVersion(
        id="v1",
        updated_at=datetime.datetime.now(),
        _size=total_ciphertext,
        message_ids=[s.message_id for s in sent],
        part_sizes=[s.size for s in sent],
    )
    recovered = await _collect(await repo.get(fv, 0, -1, "big.bin"))
    assert recovered == plaintext, "Round-trip decryption failed"


async def test_encrypting_file_message_respects_part_size():
    """EncryptingFileMessage.read() must cap output at self.size bytes.

    Directly tests the streaming wrapper without the full repository stack.
    """
    plaintext = os.urandom(30 * 1024 * 1024)  # 30 MB

    from dcfs.crypto.header import FileHeader
    from dcfs.crypto.kdf import derive_file_key

    header = FileHeader.new(chunk_size=CHUNK_SIZE)
    file_key = derive_file_key(MASTER_KEY, header.file_salt)

    inner_msg = FileMessageFromBuffer.new(buffer=plaintext, name="test.bin")
    encrypted = EncryptingFileMessage.wrap(inner_msg, file_key, header)

    # Simulate what DCMsgFileContentRepository.save() does:
    # Read all parts, each capped at PART_SIZE.
    part_size = PART_SIZE
    all_parts: list[bytes] = []
    part_index = 0

    while True:
        # Set the next part boundary
        remaining = encrypted.size - encrypted._read_size
        if remaining <= 0 and part_index > 0:
            encrypted.next_part(part_size)
        encrypted.size = part_size
        if part_index > 0:
            encrypted._read_size = 0

        # Read 1 MB at a time (like FileUploader)
        part_buf = bytearray()
        while True:
            chunk = await encrypted.read(1024 * 1024)
            if not chunk:
                break
            part_buf += chunk
        part_bytes = bytes(part_buf)
        if not part_bytes:
            break
        all_parts.append(part_bytes)
        part_index += 1

        assert len(part_bytes) <= DISCORD_MAX_FILE_SIZE, (
            f"Part {part_index} is {len(part_bytes)} bytes, "
            f"exceeds Discord limit"
        )

    assert len(all_parts) >= 2, (
        f"Expected at least 2 parts for 30MB file, got {len(all_parts)}"
    )

    # Concatenate and verify we got the full ciphertext
    full_ciphertext = b"".join(all_parts)
    expected_ciphertext_size = HEADER_SIZE + len(plaintext) + (
        (len(plaintext) + CHUNK_SIZE - 1) // CHUNK_SIZE
    ) * CHUNK_OVERHEAD

    assert len(full_ciphertext) == expected_ciphertext_size, (
        f"Total ciphertext {len(full_ciphertext)} != expected {expected_ciphertext_size}"
    )


async def test_header_present_in_first_part():
    """The DCFS encryption header must appear at byte 0 of part 1."""
    plaintext = os.urandom(5 * 1024 * 1024)  # 5 MB (single part)

    from dcfs.crypto.header import MAGIC, FileHeader
    from dcfs.crypto.kdf import derive_file_key

    header = FileHeader.new(chunk_size=CHUNK_SIZE)
    file_key = derive_file_key(MASTER_KEY, header.file_salt)

    inner_msg = FileMessageFromBuffer.new(buffer=plaintext, name="test.bin")
    encrypted = EncryptingFileMessage.wrap(inner_msg, file_key, header)

    # Don't call open() — lazy init should handle it
    buf = bytearray()
    while True:
        chunk = await encrypted.read(1024 * 1024)
        if not chunk:
            break
        buf += chunk

    assert bytes(buf[:4]) == MAGIC, "DCFS magic not found at start of ciphertext"
    assert len(buf) == encrypted.size, (
        f"Output size {len(buf)} != declared size {encrypted.size}"
    )
