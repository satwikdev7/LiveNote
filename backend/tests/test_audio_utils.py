from __future__ import annotations

import io
import math
import wave

from app.utils.audio_utils import normalize_browser_audio


def build_wav_bytes(duration_sec: float = 0.25, sample_rate: int = 16_000) -> bytes:
    frame_count = int(duration_sec * sample_rate)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return output.getvalue()


def test_normalize_browser_audio_passthrough_wav() -> None:
    wav_bytes = build_wav_bytes()
    result = normalize_browser_audio(wav_bytes, "audio/wav")

    assert result.wav_bytes[:4] == b"RIFF"
    assert result.sample_rate == 16_000
    assert result.channels == 1
    assert math.isclose(result.duration_sec, 0.25, rel_tol=0.15)
