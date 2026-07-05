import asyncio
from typing import Any


def _is_transient(ex: Exception) -> bool:
    """
    Classify a Discord upload/download error as transient (retryable) or
    permanent.

    Transient errors are those where a retry is likely to succeed after a
    short delay: rate limits (429), server errors (5xx), timeouts, and
    connection / I/O failures.  Permanent errors (4xx, ``FileSizeTooLarge``)
    should be propagated immediately.
    """
    # Late import to avoid circular dependencies – ``dcfs.errors`` is a
    # leaf module that should not import from ``dcfs.utils``.
    from dcfs.errors import FileSizeTooLarge

    if isinstance(ex, FileSizeTooLarge):
        return False

    # Discord rate-limit responses carry a ``retry_after`` attribute
    if hasattr(ex, "retry_after"):
        return True

    status: Any = getattr(ex, "status", None)
    if status is not None:
        if status == 429:  # Rate Limited
            return True
        if 500 <= status < 600:  # Server errors
            return True
        if 400 <= status < 500:  # Client errors are permanent
            return False

    if isinstance(ex, (asyncio.TimeoutError, ConnectionError, IOError)):
        return True

    return False
