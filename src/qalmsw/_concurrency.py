"""Tiny ordered parallel-map helper for LLM fan-out.

Checkers call the LLM once per item (paragraph, section). For local llama.cpp servers
started with ``--parallel N``, these calls are independent and can overlap. This helper
runs ``fn`` across ``items`` using a thread pool (the OpenAI SDK is blocking I/O, so
threads are enough) and returns results in the original order.

Falls back to a plain serial loop when ``concurrency <= 1`` so tests and single-slot
servers don't pay the thread-pool overhead.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def ordered_parallel_map(fn: Callable[[T], R], items: Iterable[T], concurrency: int) -> list[R]:
    items_list = list(items)
    if concurrency <= 1 or len(items_list) <= 1:
        return [fn(item) for item in items_list]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(fn, items_list))
