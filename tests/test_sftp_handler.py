from unittest.mock import AsyncMock, MagicMock

import asyncssh
import pytest

from dcfs.app.sftp.handler import DCFSSFTPBufferedFile


async def mock_download_gen(data_chunks):
    for chunk in data_chunks:
        yield chunk


@pytest.mark.asyncio
async def test_sftp_buffered_file_sequential_reads():
    mock_ops = MagicMock()
    # 3 chunks of 64KB
    chunk1 = b"A" * 65536
    chunk2 = b"B" * 65536
    chunk3 = b"C" * 65536

    mock_ops.download = AsyncMock(return_value=mock_download_gen([chunk1, chunk2, chunk3]))

    file_handle = DCFSSFTPBufferedFile(mock_ops, "/test.txt", "r", "client1")

    # Read 32KB at offset 0
    data1 = await file_handle.read(0, 32768)
    assert data1 == b"A" * 32768
    assert mock_ops.download.call_count == 1

    # Read next 32KB at offset 32768 (should hit buffer and NOT call download again)
    data2 = await file_handle.read(32768, 32768)
    assert data2 == b"A" * 32768
    assert mock_ops.download.call_count == 1

    # Read next 64KB at offset 65536
    data3 = await file_handle.read(65536, 65536)
    assert data3 == b"B" * 65536
    assert mock_ops.download.call_count == 1

    await file_handle.close()


@pytest.mark.asyncio
async def test_sftp_buffered_file_seek_out_of_order():
    mock_ops = MagicMock()
    chunk1 = b"0123456789"
    chunk2 = b"ABCDEFGHIJ"

    mock_ops.download = AsyncMock(
        side_effect=[
            mock_download_gen([chunk1]),
            mock_download_gen([chunk2]),
        ]
    )

    file_handle = DCFSSFTPBufferedFile(mock_ops, "/test.txt", "r", "client1")

    # Read offset 0, size 5
    d1 = await file_handle.read(0, 5)
    assert d1 == b"01234"
    assert mock_ops.download.call_count == 1

    # Jump forward out of current buffer (e.g. offset 100)
    d2 = await file_handle.read(100, 5)
    assert d2 == b"ABCDE"
    assert mock_ops.download.call_count == 2
    mock_ops.download.assert_called_with(
        "/test.txt", 100, -1, "test.txt", validate=False
    )

    await file_handle.close()


@pytest.mark.asyncio
async def test_sftp_buffered_file_eof_and_mode_checks():
    mock_ops = MagicMock()
    mock_ops.download = AsyncMock(return_value=mock_download_gen([b"short"]))

    file_handle = DCFSSFTPBufferedFile(mock_ops, "/test.txt", "r", "client1")

    # Read more bytes than available
    data = await file_handle.read(0, 100)
    assert data == b"short"

    # Write attempt on read mode should fail
    with pytest.raises(asyncssh.SFTPPermissionDenied):
        await file_handle.write(0, b"data")

    await file_handle.close()


@pytest.mark.asyncio
async def test_sftp_buffered_file_prefetch_error():
    async def mock_error_gen():
        yield b"chunk1"
        raise ValueError("Download failed")

    mock_ops = MagicMock()
    mock_ops.download = AsyncMock(return_value=mock_error_gen())

    file_handle = DCFSSFTPBufferedFile(mock_ops, "/test.txt", "r", "client1")

    # Reading raises the exception propagated from the prefetch worker
    with pytest.raises(ValueError, match="Download failed"):
        await file_handle.read(0, 100)

    await file_handle.close()


@pytest.mark.asyncio
async def test_sftp_buffered_file_pipelined_out_of_order_reads():
    mock_ops = MagicMock()
    chunk1 = b"A" * 65536  # bytes 0..65535
    chunk2 = b"B" * 65536  # bytes 65536..131071

    mock_ops.download = AsyncMock(return_value=mock_download_gen([chunk1, chunk2]))

    file_handle = DCFSSFTPBufferedFile(mock_ops, "/pipelined.txt", "r", "client1")

    # Read offset 0 first so download stream starts at 0
    data1 = await file_handle.read(0, 32768)
    assert data1 == b"A" * 32768
    assert mock_ops.download.call_count == 1

    # Pipelined request for offset 65536 arrives BEFORE request for offset 32768
    data3 = await file_handle.read(65536, 32768)
    assert data3 == b"B" * 32768
    assert mock_ops.download.call_count == 1

    # Request for offset 32768 arrives (out of order, behind current 65536 offset)
    data2 = await file_handle.read(32768, 32768)
    assert data2 == b"A" * 32768
    # Should STILL be 1 download call because byte range was retained in buffer!
    assert mock_ops.download.call_count == 1

    await file_handle.close()
