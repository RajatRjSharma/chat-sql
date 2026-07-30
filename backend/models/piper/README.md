# Piper TTS voice (offline)

Bundled English voice used by `POST /api/voice/speak` in local, Docker, and production.

| File | Purpose |
|------|---------|
| `en_US-amy-low.onnx` | Piper neural voice (~60 MB) |
| `en_US-amy-low.onnx.json` | Voice config (sample rate, phonemes) |
| `MODEL_CARD` | Upstream model card |

**Voice:** `en_US-amy-low` (English US, Amy, low quality — smaller/faster for free-tier RAM).

Source: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) (Piper / Open Home Foundation).

Refresh / re-download:

```bash
make tts-models
```

Do not download voices at request time — speak uses only these on-disk files.
