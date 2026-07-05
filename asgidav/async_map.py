import asyncio
from typing import Any, Callable, Coroutine, Iterable, List, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")


async def async_map(
    func: Callable[[T], Coroutine[Any, Any, U]],
    iterable: Iterable[T],
    max_concurrency: Optional[int] = None,
) -> List[U]:
    """
    Map an async function over an iterable, with optional concurrency limit.

    When *max_concurrency* is set, a semaphore prevents more than that many
    tasks from running at once, which avoids overwhelming the event loop for
    large directories.
    """
    if max_concurrency is None:
        tasks: List[asyncio.Task[U]] = [
            asyncio.create_task(func(item)) for item in iterable
        ]
        return await asyncio.gather(*tasks)

    sem = asyncio.Semaphore(max_concurrency)

    async def _wrapped(item: T) -> U:
        async with sem:
            return await func(item)

    tasks = [asyncio.create_task(_wrapped(item)) for item in iterable]
    results: List[U] = []
    for coro in asyncio.as_completed(tasks):
        try:
            results.append(await coro)
        except Exception as ex:
            # Cancel remaining tasks on first failure to fail fast
            for t in tasks:
                if not t.done():
                    t.cancel()
            raise ex
    return results
