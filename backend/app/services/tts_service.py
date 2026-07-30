"""Offline Piper TTS — synthesizes WAV from text with no network calls."""

from __future__ import annotations

import io
import logging
import re
import threading
import wave
from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path
import hashlib

from app.config import settings

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:])\s+")


class TtsUnavailableError(RuntimeError):
    """Raised when Piper cannot load or synthesize."""


class TtsService:
    """Lazy-loaded Piper voice singleton (one model for the process)."""

    _lock = threading.Lock()
    _voice = None
    _voice_path: Path | None = None
    _load_error: str | None = None
    _syn_config = None
    # prepared_text -> list of wav bytes (avoids re-synthesis on prefetch+play)
    _wav_cache: OrderedDict[str, list[bytes]] = OrderedDict()
    _WAV_CACHE_MAX = 24

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            cls._voice = None
            cls._voice_path = None
            cls._load_error = None
            cls._syn_config = None
            cls._wav_cache.clear()

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
    def status(cls) -> dict[str, str | bool | float | int]:
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
            "max_chars": settings.tts_max_chars,
            "first_chunk_chars": settings.tts_first_chunk_chars,
            "length_scale": settings.tts_length_scale,
            "onnx_threads": settings.tts_onnx_threads,
        }

    @classmethod
    def _build_syn_config(cls):
        from piper import SynthesisConfig

        return SynthesisConfig(length_scale=settings.tts_length_scale)

    @classmethod
    def _load_voice_with_thread_limit(cls, path: Path):
        """Load Piper with ONNX Runtime pinned to a small thread count (Render-friendly)."""
        import onnxruntime as ort
        from piper import PiperVoice

        threads = max(1, settings.tts_onnx_threads)
        real_session = ort.InferenceSession

        def limited_session(model_or_path, sess_options=None, providers=None, **kwargs):
            opts = sess_options or ort.SessionOptions()
            opts.intra_op_num_threads = threads
            opts.inter_op_num_threads = 1
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            return real_session(
                model_or_path,
                sess_options=opts,
                providers=providers,
                **kwargs,
            )

        ort.InferenceSession = limited_session  # type: ignore[misc, assignment]
        try:
            return PiperVoice.load(str(path))
        finally:
            ort.InferenceSession = real_session  # type: ignore[misc, assignment]

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
                logger.info(
                    "Loading Piper voice from %s (onnx_threads=%s, length_scale=%s)",
                    path,
                    settings.tts_onnx_threads,
                    settings.tts_length_scale,
                )
                cls._voice = cls._load_voice_with_thread_limit(path)
                cls._syn_config = cls._build_syn_config()
                cls._voice_path = path
                cls._load_error = None
                logger.info("Piper voice ready (%s)", path.name)
            except Exception as exc:  # noqa: BLE001 — surface as unavailable
                cls._load_error = f"Failed to load Piper voice: {exc}"
                logger.exception("Piper voice load failed")
                return None
            return cls._voice

    @classmethod
    def _warmup(cls) -> None:
        if not settings.tts_warmup_enabled:
            return
        phrase = (settings.tts_warmup_text or "Ready.").strip() or "Ready."
        try:
            voice = cls._voice
            if voice is None:
                return
            _ = cls._wav_from_text(phrase, voice)
            logger.info("Piper warmup complete (%r)", phrase)
        except Exception:  # noqa: BLE001
            logger.exception("Piper warmup failed (non-fatal)")

    @classmethod
    def preload(cls) -> bool:
        """Load the voice at startup and optionally run a one-shot warmup synthesize."""
        ready = cls._ensure_voice() is not None
        if ready:
            cls._warmup()
        return ready

    @staticmethod
    def prepare_text(raw: str) -> str:
        """Normalize text for speech. Does not truncate — full paragraph is kept."""
        text = (raw or "").strip()
        if not text:
            return ""
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[*_`#]+", "", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _split_oversized(piece: str, limit: int) -> list[str]:
        """Split a long sentence into chunks that fit under limit (never drops text)."""
        piece = piece.strip()
        if not piece:
            return []
        if len(piece) <= limit:
            return [piece]

        # Prefer clause boundaries (comma / semicolon / colon + space).
        clauses = [c.strip() for c in _CLAUSE_SPLIT.split(piece) if c.strip()]
        if len(clauses) > 1:
            out: list[str] = []
            buf = ""
            for clause in clauses:
                candidate = f"{buf} {clause}".strip() if buf else clause
                if len(candidate) <= limit:
                    buf = candidate
                    continue
                if buf:
                    out.append(buf)
                if len(clause) <= limit:
                    buf = clause
                else:
                    out.extend(TtsService._split_by_words(clause, limit))
                    buf = ""
            if buf:
                out.append(buf)
            return out

        return TtsService._split_by_words(piece, limit)

    @staticmethod
    def _split_by_words(piece: str, limit: int) -> list[str]:
        words = piece.split()
        if not words:
            return []
        out: list[str] = []
        buf = ""
        for word in words:
            candidate = f"{buf} {word}".strip() if buf else word
            if len(candidate) <= limit:
                buf = candidate
                continue
            if buf:
                out.append(buf)
            if len(word) <= limit:
                buf = word
            else:
                # Extremely long token — hard-slice so nothing is dropped.
                for i in range(0, len(word), limit):
                    out.append(word[i : i + limit])
                buf = ""
        if buf:
            out.append(buf)
        return out

    @classmethod
    def split_sentences(cls, raw: str) -> list[str]:
        """
        Split the full answer into speakable chunks.

        Covers the entire paragraph: sentences first, then oversized pieces are
        split further. Nothing is truncated away.
        """
        cleaned = cls.prepare_text(raw)
        if not cleaned:
            return []

        limit = settings.tts_max_chars
        parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p.strip()]
        if not parts:
            parts = [cleaned]

        # Merge tiny fragments into the previous sentence (e.g. abbreviations).
        merged: list[str] = []
        for part in parts:
            if merged and len(part) < 12 and part[-1:] not in ".!?":
                merged[-1] = f"{merged[-1]} {part}"
            else:
                merged.append(part)

        chunks: list[str] = []
        for part in merged:
            chunks.extend(cls._split_oversized(part, limit))

        # Prefer a short first chunk so time-to-first-audio is lower on small CPUs.
        first_cap = min(settings.tts_first_chunk_chars, limit)
        if chunks and len(chunks[0]) > first_cap:
            head = cls._split_oversized(chunks[0], first_cap)
            chunks = head + chunks[1:]

        return chunks or [cleaned]

    @classmethod
    def _wav_from_text(cls, text: str, voice) -> bytes:
        if cls._syn_config is None:
            cls._syn_config = cls._build_syn_config()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=cls._syn_config)
        return buf.getvalue()

    @classmethod
    def synthesize(cls, text: str) -> bytes:
        """
        Synthesize the full text as one WAV by concatenating chunk WAVs.
        Prefer speak-stream for progressive playback.
        """
        chunks = cls.split_sentences(text)
        if not chunks:
            raise ValueError("Text is empty")

        voice = cls._ensure_voice()
        if voice is None:
            raise TtsUnavailableError(cls._load_error or "TTS unavailable")

        if len(chunks) == 1:
            return cls._wav_from_text(chunks[0], voice)

        # Concatenate PCM frames from each chunk WAV into one file.
        frames = bytearray()
        params = None
        for chunk in chunks:
            piece = cls._wav_from_text(chunk, voice)
            with wave.open(io.BytesIO(piece), "rb") as wf:
                if params is None:
                    params = wf.getparams()
                frames.extend(wf.readframes(wf.getnframes()))

        if params is None:
            raise TtsUnavailableError("TTS produced no audio")

        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setparams(params)
            wf.writeframes(bytes(frames))
        return out.getvalue()

    @classmethod
    def _cache_key(cls, cleaned: str) -> str:
        return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    @classmethod
    def _cache_get(cls, cleaned: str) -> list[bytes] | None:
        key = cls._cache_key(cleaned)
        with cls._lock:
            wavs = cls._wav_cache.get(key)
            if wavs is None:
                return None
            cls._wav_cache.move_to_end(key)
            return list(wavs)

    @classmethod
    def _cache_put(cls, cleaned: str, wavs: list[bytes]) -> None:
        key = cls._cache_key(cleaned)
        with cls._lock:
            cls._wav_cache[key] = list(wavs)
            cls._wav_cache.move_to_end(key)
            while len(cls._wav_cache) > cls._WAV_CACHE_MAX:
                cls._wav_cache.popitem(last=False)

    @classmethod
    def synthesize_sentences(cls, text: str) -> Iterator[tuple[int, int, bytes]]:
        """
        Yield (index, total, wav_bytes) for every chunk so the full paragraph
        is spoken progressively. Results are cached so Play after prefetch is free.
        """
        cleaned = cls.prepare_text(text)
        if not cleaned:
            raise ValueError("Text is empty")

        cached = cls._cache_get(cleaned)
        if cached is not None:
            total = len(cached)
            for index, wav in enumerate(cached):
                yield index, total, wav
            return

        sentences = cls.split_sentences(cleaned)
        if not sentences:
            raise ValueError("Text is empty")

        voice = cls._ensure_voice()
        if voice is None:
            raise TtsUnavailableError(cls._load_error or "TTS unavailable")

        total = len(sentences)
        wavs: list[bytes] = []
        for index, sentence in enumerate(sentences):
            wav = cls._wav_from_text(sentence, voice)
            wavs.append(wav)
            yield index, total, wav
        cls._cache_put(cleaned, wavs)
