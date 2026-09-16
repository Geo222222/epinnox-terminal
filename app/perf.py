from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_MAX_WORKERS = max(1, int(os.getenv("EPINNOX_COMPUTE_WORKERS", "2")))
COMPUTE_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="epinnox-compute")


async def run_compute(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run CPU/blocking research work away from the FastAPI event loop.

    A bounded executor prevents scanner/backtest bursts from creating an unbounded
    number of worker threads on a workstation.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(COMPUTE_EXECUTOR, partial(func, *args, **kwargs))
