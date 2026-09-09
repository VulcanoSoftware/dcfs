"""Measure where DCFS download throughput is actually lost.

Runs against a live DCFS configuration (same config file the server uses) and
reports throughput for each layer of the download path, so a slow transfer can
be attributed to the Discord CDN, to DCFS's own plumbing, or to the protocol
server on top of it.

Usage:

    DCFS_CONFIG_FILE=config.yaml python -m tools.bench_download /client/path/file.bin

Reported measurements:

* ``dcfs full download``   -- everything DCFS does for an SFTP/WebDAV read:
                              metadata, decryption, part ordering, parallel
                              CDN range requests.
* ``cdn single connection`` -- one plain HTTP GET of one 8 MB part. This is the
                              per-connection speed Discord gives this host.
* ``cdn N connections``    -- the same part fetched as N parallel byte ranges.
                              If this is not ~N times the single-connection
                              number, the link (or Discord) is the ceiling and
                              no amount of client-side parallelism will help.
"""

import asyncio
import logging
import sys
import time
from typing import Optional

import aiohttp

from dcfs.config import get_config
from dcfs.core import Clients, Ops
from dcfs.utils.others import is_big_file

logger = logging.getLogger(__name__)

PARALLEL_PROBES = (1, 4, 8, 16)


def _mbps(nbytes: int, seconds: float) -> float:
    return nbytes / seconds / 1e6 if seconds > 0 else 0.0


async def _time_stream(stream) -> tuple[int, float]:
    t0 = time.monotonic()
    total = 0
    async for chunk in stream:
        total += len(chunk)
    return total, time.monotonic() - t0


async def _bench_dcfs(ops: Ops, path: str, limit: int) -> None:
    stream = await ops.download(path, 0, limit - 1, "bench", validate=False)
    total, dt = await _time_stream(stream)
    logger.info(
        f"dcfs full download      {_mbps(total, dt):8.1f} MB/s "
        f"({total / 1e6:.0f} MB in {dt:.1f}s)"
    )


async def _bench_cdn(url: str, size: int) -> None:
    async with aiohttp.ClientSession() as session:

        async def fetch(begin: int, end: int) -> int:
            headers = {"Range": f"bytes={begin}-{end}"}
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                got = 0
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    got += len(chunk)
                return got

        for n in PARALLEL_PROBES:
            per = size // n
            ranges = [(i * per, (i + 1) * per - 1) for i in range(n)]
            t0 = time.monotonic()
            totals = await asyncio.gather(*[fetch(b, e) for b, e in ranges])
            dt = time.monotonic() - t0
            label = "cdn single connection" if n == 1 else f"cdn {n} connections"
            logger.info(
                f"{label:23s} {_mbps(sum(totals), dt):8.1f} MB/s "
                f"({sum(totals) / 1e6:.0f} MB in {dt:.1f}s)"
            )


async def _first_part_url(ops: Ops, path: str) -> Optional[tuple[str, int]]:
    """Resolve the CDN URL and size of the file's first Discord part."""
    fd = await ops.desc(path, validate=False)
    fv = fd.get_latest_version()
    if not fv.message_ids:
        return None
    repo = ops._client.fc_repo
    # Unwrap the encryption decorator if it is installed.
    repo = getattr(repo, "_inner", repo)
    message_api = repo._message_api  # type: ignore[union-attr]
    bot = message_api.discord_api.next_bot
    channel = await bot._get_channel(  # type: ignore[attr-defined]
        bot._parse_channel_id(message_api.private_file_channel)  # type: ignore[attr-defined]
    )
    attachment = await bot._resolve_attachment(  # type: ignore[attr-defined]
        channel, fv.message_ids[0]
    )
    return attachment.url, attachment.size


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        logger.info(__doc__)
        return 2

    path = argv[1]
    limit_mb = int(argv[2]) if len(argv) > 2 else 64

    # Imported lazily so the module can be read without a Discord login.
    from main import create_clients

    config = get_config()
    clients: Clients = await create_clients(config)

    client_name, _, sub_path = path.lstrip("/").partition("/")
    if client_name not in clients:
        logger.info(f"unknown client '{client_name}'; known: {', '.join(clients)}")
        return 2

    ops = Ops(clients[client_name])
    sub_path = "/" + sub_path

    resolved = await _first_part_url(ops, sub_path)
    if resolved:
        logger.info(
            f"part size {resolved[1] / 1e6:.1f} MB, "
            f"parallel range split enabled: {is_big_file(resolved[1])}"
        )
    else:
        logger.info("no parts found")

    await _bench_dcfs(ops, sub_path, limit_mb * 1024 * 1024)
    if resolved:
        await _bench_cdn(*resolved)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("discord").setLevel(logging.WARNING)
    sys.exit(asyncio.run(main(sys.argv)))
