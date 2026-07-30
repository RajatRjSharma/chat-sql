"""Offline voice TTS routes (Piper)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.voice import SpeakRequest, TtsStatusResponse
from app.security.rate_limit import enforce_tts_rate_limit
from app.services.tts_service import TtsService, TtsUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/status", response_model=TtsStatusResponse)
async def tts_status(
    current_user: User = Depends(get_current_user),
) -> TtsStatusResponse:
    """Report whether offline Piper TTS is ready (auth required)."""
    _ = current_user
    return TtsStatusResponse(**TtsService.status())


@router.post("/speak")
async def speak(
    body: SpeakRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Synthesize a single WAV from the full text (legacy / simple clients).
    Prefer POST /api/voice/speak-stream for lower time-to-first-audio.
    """
    enforce_tts_rate_limit(request, user_id=str(current_user.id))

    if not TtsService.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech is unavailable on this server.",
        )

    try:
        audio = await asyncio.to_thread(TtsService.synthesize, body.text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except TtsUnavailableError as exc:
        logger.warning("TTS unavailable for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech is unavailable on this server.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("TTS synthesize failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not synthesize speech. Please try again.",
        ) from exc

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


def _sentence_ndjson_sync(text: str, *, total_hint: int) -> Iterator[bytes]:
    """Yield NDJSON lines as each sentence WAV is ready."""
    # Flush connection early so the client sees bytes before ONNX finishes.
    yield (
        json.dumps({"phase": "start", "n": total_hint}, separators=(",", ":")) + "\n"
    ).encode("utf-8")

    for index, total, wav in TtsService.synthesize_sentences(text):
        payload = {
            "i": index,
            "n": total,
            "audio": base64.b64encode(wav).decode("ascii"),
        }
        yield (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


async def _sentence_ndjson(text: str, *, total_hint: int) -> AsyncIterator[bytes]:
    """
    Run Piper sentence synthesis on a worker thread and forward lines ASAP.
    Uses a queue so the HTTP response starts after the first sentence, not the last.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def worker() -> None:
        try:
            for chunk in _sentence_ndjson_sync(text, total_hint=total_hint):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:  # noqa: BLE001
            err = {"error": str(exc)[:200]}
            line = (json.dumps(err, separators=(",", ":")) + "\n").encode("utf-8")
            loop.call_soon_threadsafe(queue.put_nowait, line)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker_task = asyncio.create_task(asyncio.to_thread(worker))
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        await worker_task


@router.post("/speak-stream")
async def speak_stream(
    body: SpeakRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream sentence-level WAV chunks as NDJSON (one JSON object per line).

    Each audio line: {"i":0,"n":3,"audio":"<base64-wav>"}
    First line may be {"phase":"start","n":3} to flush the connection early.
    """
    enforce_tts_rate_limit(request, user_id=str(current_user.id))

    if not TtsService.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech is unavailable on this server.",
        )

    sentences = TtsService.split_sentences(body.text)
    if not sentences:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Text is empty",
        )

    return StreamingResponse(
        _sentence_ndjson(body.text, total_hint=len(sentences)),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-TTS-Sentences": str(len(sentences)),
        },
    )
