import os

import pytest

from dcfs.core.model import DCFSFileVersion
from dcfs.core.repository.interface import IFileContentRepository
from dcfs.crypto.repository import EncryptingFileContentRepository
from dcfs.reqres import (
    FileContent,
    FileMessageFromBuffer,
    SentFileMessage,
    UploadableFileMessage,
)

# Reuse the same constants for consistency
MASTER_KEY = b"\x77" * 32
CHUNK_SIZE = 64 * 1024
PART_SIZE = 1 * 1024 * 1024  # 1 MB parts for testing

class FailingInMemoryRepo(IFileContentRepository):
    """A repository that fails on the second part once, then succeeds."""
    def __init__(self):
        self.parts = {}
        self.fail_count = 0
        self.part_sizes_observed = []

    async def save(self, file_msg: UploadableFileMessage) -> list[SentFileMessage]:
        size = file_msg.get_size()
        res = []

        # We'll manually partition it to simulate DCMsgFileContentRepository.save
        remaining_total = size
        part_idx = 0

        while remaining_total > 0:
            current_part_size = min(PART_SIZE, remaining_total)
            file_msg.size = current_part_size
            file_msg.name = f"part{part_idx}"

            # Simulate a retry loop for each part
            retries = 0
            while retries < 3:
                try:
                    await file_msg.open()

                    # If this is the second part (idx 1) and we haven't failed yet, fail now.
                    if part_idx == 1 and self.fail_count == 0:
                        self.fail_count += 1
                        # Read half of it before failing
                        await file_msg.read(current_part_size // 2)
                        raise Exception("Simulated transient failure")

                    # Otherwise, read the full part
                    buf = bytearray()
                    while len(buf) < current_part_size:
                        chunk = await file_msg.read(64 * 1024)
                        if not chunk:
                            break
                        buf += chunk

                    self.parts[part_idx] = bytes(buf)
                    self.part_sizes_observed.append(len(buf))
                    res.append(SentFileMessage(message_id=part_idx, size=len(buf)))
                    break
                except Exception:
                    retries += 1
                    if retries >= 3:
                        raise

            remaining_total -= current_part_size
            part_idx += 1
            if remaining_total > 0:
                file_msg.next_part(current_part_size)

        return res

    async def get(self, fv: DCFSFileVersion, begin: int, end: int, name: str) -> FileContent:
        ciphertext = b"".join(self.parts.values())
        if end < 0:
            end = len(ciphertext) - 1

        async def stream():
            yield ciphertext[begin : end + 1]

        return stream()

    async def update(self, message_id: int, buffer: bytes, name: str) -> int:
        self.parts[message_id] = buffer
        return len(buffer)

@pytest.mark.asyncio
async def test_encrypted_upload_retry_consistency():
    """Verify that EncryptingFileMessage handles retries of a failed part correctly."""
    # 5 MB file = 5 parts of 1 MB
    plaintext = os.urandom(5 * 1024 * 1024)
    file_msg = FileMessageFromBuffer.new(buffer=plaintext, name="retry.bin")

    inner_repo = FailingInMemoryRepo()
    repo = EncryptingFileContentRepository(
        inner_repo, master_key=MASTER_KEY, chunk_size=CHUNK_SIZE
    )

    # This will trigger the failure and retry in FailingInMemoryRepo.save
    sent = await repo.save(file_msg)

    assert inner_repo.fail_count == 1
    assert len(sent) == len(inner_repo.parts)

    # Verify the final assembled ciphertext is correct by decrypting it
    import datetime

    from dcfs.core.model import DCFSFileVersion

    total_size = sum(s.size for s in sent)
    fv = DCFSFileVersion(
        id="v1",
        updated_at=datetime.datetime.now(),
        _size=total_size,
        message_ids=[s.message_id for s in sent],
        part_sizes=[s.size for s in sent],
    )

    async def collect(stream):
        buf = bytearray()
        async for piece in stream:
            buf += piece
        return bytes(buf)

    recovered = await collect(await repo.get(fv, 0, -1, "retry.bin"))
    assert recovered == plaintext, "Decryption failed after retry - data corruption!"
