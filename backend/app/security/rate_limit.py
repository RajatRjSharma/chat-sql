"""In-memory sliding-window rate limiter (stateless app; per-process)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import settings

# Cap distinct keys so long-lived processes do not retain stale IP buckets forever.
_MAX_KEYS = 2_048


class _SlidingWindowLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait and try again.",
                    headers={"Retry-After": str(window_seconds)},
                )
            bucket.append(now)
            self._prune_locked(now, window_seconds)

    def _prune_locked(self, now: float, window_seconds: int) -> None:
        """Drop empty / excess keys (unbounded growth guard)."""
        if len(self._hits) < _MAX_KEYS // 2:
            return
        if len(self._hits) <= _MAX_KEYS:
            empty = [k for k, b in self._hits.items() if not b]
            for k in empty[:64]:
                self._hits.pop(k, None)
            return

        cutoff = now - window_seconds
        stale: list[str] = []
        for k, bucket in self._hits.items():
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if not bucket:
                stale.append(k)
        for k in stale:
            self._hits.pop(k, None)
        while len(self._hits) > _MAX_KEYS:
            self._hits.pop(next(iter(self._hits)), None)


_limiter = _SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    limit: int,
    identity: str = "",
    window_seconds: int = 60,
) -> None:
    """Limit abuse per IP (+ optional identity) for a named scope."""
    ip = client_ip(request)
    _limiter.check(f"{scope}:ip:{ip}", limit=limit, window_seconds=window_seconds)
    if identity:
        _limiter.check(
            f"{scope}:id:{identity.lower()}",
            limit=max(3, limit // 2),
            window_seconds=window_seconds,
        )


def enforce_auth_rate_limit(request: Request, *, action: str, identity: str = "") -> None:
    """Limit auth abuse per IP (+ optional identity like email)."""
    enforce_rate_limit(
        request,
        scope=f"auth:{action}",
        limit=settings.auth_rate_limit_per_minute,
        identity=identity,
    )


def enforce_connect_rate_limit(request: Request, *, user_id: str) -> None:
    enforce_rate_limit(
        request,
        scope="data:connect",
        limit=settings.connect_rate_limit_per_minute,
        identity=user_id,
    )


def enforce_upload_rate_limit(request: Request, *, user_id: str) -> None:
    enforce_rate_limit(
        request,
        scope="data:upload",
        limit=settings.upload_rate_limit_per_minute,
        identity=user_id,
    )


def enforce_chat_rate_limit(request: Request, *, user_id: str) -> None:
    enforce_rate_limit(
        request,
        scope="chat:ask",
        limit=settings.chat_rate_limit_per_minute,
        identity=user_id,
    )


def enforce_embed_rate_limit(request: Request, *, user_id: str) -> None:
    enforce_rate_limit(
        request,
        scope="data:embed",
        limit=settings.embed_rate_limit_per_minute,
        identity=user_id,
    )


def enforce_tts_rate_limit(request: Request, *, user_id: str) -> None:
    enforce_rate_limit(
        request,
        scope="voice:speak",
        limit=settings.tts_rate_limit_per_minute,
        identity=user_id,
    )
