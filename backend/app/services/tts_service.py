"""Offline Piper TTS — synthesizes WAV from text with no network calls."""

from __future__ import annotations

import io
import logging
import re
import threading
import wave
from collections.abc import Iterator
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class TtsUnavailableError(RuntimeError):
    """Raised when Piper cannot load or synthesize."""


class TtsService:
    """Lazy-loaded Piper voice singleton (one model for the process)."""

    _lock = threading.Lock()
    _voice = None
    _voice_path: Path | None = None
    _load_error: str | None = None

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            cls._voice = None
            cls._voice_path = None
            cls._load_error = None

    @classmethod
    def is_available(cls) -> bool:
        if not settings.tts_enabled:
            return False
        if cls._load_error:
            return False
        if cls._voice is not None:
            return True
        path = settings.resolved_tts_voice_path
        return path.is_file()

    @classmethod
    def status(cls) -> dict[str, str | bool]:
        path = settings.resolved_tts_voice_path
        available = False
        if settings.tts_enabled and cls._load_error is None:
            if cls._voice is not None:
                available = True
            elif path.is_file():
                available = cls._ensure_voice() is not None
        return {
            "enabled": settings.tts_enabled,
            "available": available,
            "voice_path": str(path),
            "voice_present": path.is_file(),
            "error": cls._load_error or "",
        }

    @classmethod
    def _ensure_voice(cls):
        if not settings.tts_enabled:
            cls._load_error = "TTS is disabled"
            return None
        if cls._voice is not None:
            return cls._voice
        if cls._load_error:
            return None

        with cls._lock:
            if cls._voice is not None:
                return cls._voice
            if cls._load_error:
                return None

            path = settings.resolved_tts_voice_path
            if not path.is_file():
                cls._load_error = f"Voice model not found: {path}"
                logger.warning(cls._load_error)
                return None

            try:
                from piper import PiperVoice

                logger.info("Loading Piper voice from %s", path)
                cls._voice = PiperVoice.load(str(path))
                cls._voice_path = path
                cls._load_error = None
                logger.info("Piper voice ready (%s)", path.name)
            except Exception as exc:  # noqa: BLE001 — surface as unavailable
                cls._load_error = f"Failed to load Piper voice: {exc}"
                logger.exception("Piper voice load failed")
                return None
            return cls._voice

    @classmethod
    def preload(cls) -> bool:
        """Load the voice at startup. Returns True if ready."""
        return cls._ensure_voice() is not None

    @staticmethod
    def prepare_text(raw: str, *, max_chars: int | None = None) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[*_`#]+", "", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text).strip()
        limit = max_chars if max_chars is not None else settings.tts_max_chars
        if len(text) > limit:
            text = text[: limit - 1].rstrip() + "…"
        return text

    @classmethod
    def split_sentences(cls, raw: str) -> list[str]:
        """Normalize text then split into speakable sentence chunks."""
        cleaned = cls.prepare_text(raw)
        if not cleaned:
            return []
        parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p.strip()]
        if not parts:
            return [cleaned]
        # Merge tiny fragments into the previous sentence (e.g. abbreviations).
        merged: list[str] = []
        for part in parts:
            if merged and len(part) < 12 and part[-1:] not in ".!?":
                merged[-1] = f"{merged[-1]} {part}"
            else:
                merged.append(part)
        return merged or [cleaned]

    @classmethod
    def _wav_from_text(cls, text: str, voice) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return buf.getvalue()

    @classmethod
    def synthesize(cls, text: str) -> bytes:
        cleaned = cls.prepare_text(text)
        if not cleaned:
            raise ValueError("Text is empty")

        voice = cls._ensure_voice()
        if voice is None:
            raise TtsUnavailableError(cls._load_error or "TTS unavailable")

        return cls._wav_from_text(cleaned, voice)

    @classmethod
    def synthesize_sentences(cls, text: str) -> Iterator[tuple[int, int, bytes]]:
        """
        Yield (index, total, wav_bytes) per sentence so callers can stream
        audio before the full summary is synthesized.
        """
        sentences = cls.split_sentences(text)
        if not sentences:
            raise ValueError("Text is empty")

        voice = cls._ensure_voice()
        if voice is None:
            raise TtsUnavailableError(cls._load_error or "TTS unavailable")

        total = len(sentences)
        for index, sentence in enumerate(sentences):
            yield index, total, cls._wav_from_text(sentence, voice)
