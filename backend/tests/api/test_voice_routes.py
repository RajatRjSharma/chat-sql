"""API tests for offline Piper TTS routes."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.tts_service import TtsService, TtsUnavailableError


class TestVoiceSpeakRoute:
    def setup_method(self) -> None:
        TtsService.reset_for_tests()

    def teardown_method(self) -> None:
        TtsService.reset_for_tests()

    def test_speak_returns_wav(self, client: TestClient) -> None:
        fake_wav = b"RIFF....WAVEfmt "
        with (
            patch.object(TtsService, "is_available", return_value=True),
            patch.object(TtsService, "synthesize", return_value=fake_wav) as synth,
        ):
            response = client.post(
                "/api/voice/speak",
                json={"text": "Total sales were higher in the West."},
            )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/wav")
        assert response.content == fake_wav
        synth.assert_called_once()

    def test_speak_empty_text_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/voice/speak", json={"text": ""})
        assert response.status_code == 422

    def test_speak_unavailable_returns_503(self, client: TestClient) -> None:
        with patch.object(TtsService, "is_available", return_value=False):
            response = client.post("/api/voice/speak", json={"text": "hello"})
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    def test_speak_synthesize_error_returns_503(self, client: TestClient) -> None:
        with (
            patch.object(TtsService, "is_available", return_value=True),
            patch.object(
                TtsService,
                "synthesize",
                side_effect=TtsUnavailableError("missing model"),
            ),
        ):
            response = client.post("/api/voice/speak", json={"text": "hello"})
        assert response.status_code == 503

    def test_status_endpoint(self, client: TestClient) -> None:
        with patch.object(
            TtsService,
            "status",
            return_value={
                "enabled": False,
                "available": False,
                "voice_path": "/tmp/voice.onnx",
                "voice_present": False,
                "error": "TTS is disabled",
                "max_chars": 220,
                "first_chunk_chars": 90,
                "length_scale": 0.85,
                "onnx_threads": 1,
            },
        ):
            response = client.get("/api/voice/status")
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        assert body["available"] is False
        assert body["length_scale"] == 0.85

    def test_speak_stream_returns_ndjson_sentences(self, client: TestClient) -> None:
        wav_a = b"RIFF_A"
        wav_b = b"RIFF_B"

        def fake_sentences(text: str):
            yield 0, 2, wav_a
            yield 1, 2, wav_b

        with (
            patch.object(TtsService, "is_available", return_value=True),
            patch.object(
                TtsService,
                "split_sentences",
                return_value=["One.", "Two."],
            ),
            patch.object(
                TtsService,
                "synthesize_sentences",
                side_effect=fake_sentences,
            ),
        ):
            response = client.post(
                "/api/voice/speak-stream",
                json={"text": "One. Two."},
            )
        assert response.status_code == 200
        assert "ndjson" in response.headers["content-type"]
        lines = [ln for ln in response.text.strip().split("\n") if ln.strip()]
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["i"] == 0 and first["n"] == 2
        assert second["i"] == 1 and second["n"] == 2
        assert base64.b64decode(first["audio"]) == wav_a
        assert base64.b64decode(second["audio"]) == wav_b


class TestTtsServicePrepareText:
    def test_strips_markdown(self) -> None:
        text = TtsService.prepare_text("  **Hello**  world  ")
        assert "Hello" in text
        assert "**" not in text

    def test_empty(self) -> None:
        assert TtsService.prepare_text("   ") == ""

    def test_prepare_keeps_full_paragraph(self) -> None:
        text = (
            "In the PostgreSQL sales schema, the orders table contains 800 orders "
            "totaling $278,924.15, with an average order value of $348.66. "
            "The earliest order dates back to January 1 2024, while the most "
            "recent is June 23 2025. Of these, 466 orders have been completed "
            "and 169 have been cancelled."
        )
        assert TtsService.prepare_text(text) == " ".join(text.split())

    def test_split_covers_full_paragraph(self) -> None:
        text = (
            "In the PostgreSQL sales schema, the orders table contains 800 orders "
            "totaling $278,924.15, with an average order value of $348.66. "
            "The earliest order dates back to January 1 2024, while the most "
            "recent is June 23 2025. Of these, 466 orders have been completed "
            "and 169 have been cancelled."
        )
        parts = TtsService.split_sentences(text)
        joined = " ".join(parts)
        assert "cancelled" in joined
        assert "while the most recent" in joined
        assert "$348.66" in joined
        assert "…" not in joined
        assert len(parts[0]) <= 90
        for part in parts[1:]:
            assert len(part) <= 220

    def test_split_sentences(self) -> None:
        parts = TtsService.split_sentences(
            "West led sales. East was second. North trailed."
        )
        assert len(parts) == 3
        assert parts[0].endswith(".")
        assert "East" in parts[1]
