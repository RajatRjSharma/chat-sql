"""API tests for offline Piper TTS routes."""

from __future__ import annotations

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
            },
        ):
            response = client.get("/api/voice/status")
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        assert body["available"] is False


class TestTtsServicePrepareText:
    def test_strips_and_truncates(self) -> None:
        text = TtsService.prepare_text("  **Hello**  world  ", max_chars=20)
        assert "Hello" in text
        assert "**" not in text

    def test_empty(self) -> None:
        assert TtsService.prepare_text("   ") == ""

    def test_truncation_adds_ellipsis(self) -> None:
        long = "a" * 100
        out = TtsService.prepare_text(long, max_chars=20)
        assert len(out) <= 20
        assert out.endswith("…")
