"""Voice / TTS request schemas."""

from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class TtsStatusResponse(BaseModel):
    enabled: bool
    available: bool
    voice_path: str
    voice_present: bool
    error: str = ""
    max_chars: int = 220
    length_scale: float = 0.85
    onnx_threads: int = 1
