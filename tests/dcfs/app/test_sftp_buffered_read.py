from unittest.mock import MagicMock

import pytest

from dcfs.app.sftp.handler import DCFSSFTPBufferedFile

DATA = bytes((i * 7) % 251 for i in range(6 * 1024 * 1024))
CHUNK = 64 * 1024


def _file(data: bytes = DATA) -> tuple[DCFSSFTPBufferedFile, list[int]]:
    ops = MagicMock()
    downloads: list[int] = []

    async def download(path, offset, end, name, validate=False):
        downloads.append(offset)

        async def gen():
            for pos in range(offset, len(data), CHUNK):
                yield data[pos : pos + CHUNK]

        return gen()

    ops.download = download
    return DCFSSFTPBufferedFile(ops, "/c/file.bin", "r", "c"), downloads


@pytest.mark.asyncio
async def test_sequential_reads_return_the_whole_file():
    f, downloads = _file()
    out = bytearray()
    offset = 0
    while True:
        data = await f.read(offset, 256 * 1024)
        if not data:
            break
        out += data
        offset += len(data)

    assert bytes(out) == DATA
    assert downloads[0] == 0


@pytest.mark.asyncio
async def test_read_spanning_chunk_boundaries():
    f, _ = _file()
    await f.read(0, 10)
    data = await f.read(CHUNK - 5, CHUNK + 10)

    assert data == DATA[CHUNK - 5 : 2 * CHUNK + 5]


@pytest.mark.asyncio
async def test_backward_seek_restarts_the_stream():
    f, downloads = _file()
    far = DCFSSFTPBufferedFile.MAX_BACKWARD_RETAIN + 512 * 1024
    offset = 0
    while offset < far:
        offset += len(await f.read(offset, 256 * 1024))

    data = await f.read(0, 32)

    assert data == DATA[:32]
    assert downloads == [0, 0]


@pytest.mark.asyncio
async def test_read_past_end_of_file_returns_empty():
    f, _ = _file(data=DATA[: 8 * 1024])
    assert await f.read(16 * 1024, 1024) == b""
