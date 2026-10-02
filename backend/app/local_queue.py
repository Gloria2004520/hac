from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from app.config import settings


executor = ThreadPoolExecutor(
    max_workers=settings.local_workers,
    thread_name_prefix="video-download",
)


def submit(function: Callable[..., Any], *args: Any) -> Future:
    return executor.submit(function, *args)
