"""Offline voice TTS routes (Piper)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

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
    Synthesize WAV audio from text using the bundled Piper voice.
    Fully offline at request time — no external TTS APIs.
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
