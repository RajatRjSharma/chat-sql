"""Avoid stacking chat + TTS peak RAM without slowing the happy path.

Render free tier is ~512MB. Holding a lock for an entire Speak *or* SSE
stream would stall the other; instead we only serialize short critical
sections (model load / single chunk synth / one graph invoke).

Forced ``gc.collect()`` runs only after TTS sections by default — never on
the chat path (full GC can add multi‑ms pauses). Chat frees memory by
dropping refs so the normal allocator / GC cycle reclaims without stalls.
"""

from __future__ import annotations

import gc
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_lock = threading.RLock()


@contextmanager
def heavy_memory_op(label: str, *, collect: bool | None = None) -> Iterator[None]:
    """Hold the process-wide heavy-op lock for the duration of *label*."""
    # Default: GC only after TTS. Chat must pass collect=True explicitly
    # if ever needed — do not imply collect from the label name.
    should_collect = label.startswith("tts") if collect is None else collect
    logger.debug("heavy_memory_op acquire: %s", label)
    _lock.acquire()
    try:
        yield
    finally:
        if should_collect:
            try:
                gc.collect()
            except Exception:  # noqa: BLE001 — never fail the caller on GC
                pass
        _lock.release()
        logger.debug("heavy_memory_op release: %s", label)
