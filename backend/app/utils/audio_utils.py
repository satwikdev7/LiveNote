from __future__ import annotations

import io
import subprocess
import wave
from dataclasses import dataclass


TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2


@dataclass
class AudioConversionResult:
    wav_bytes: bytes
    sample_rate: int
    channels: int
    duration_sec: float


def _read_wav_metadata(raw_audio: bytes) -> tuple[int, int, int]:
    with wave.open(io.BytesIO(raw_audio), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        frame_count = wav_file.getnframes()
    return frame_rate, channels, frame_count


def _passthrough_wav(raw_audio: bytes) -> AudioConversionResult:
    frame_rate, channels, frame_count = _read_wav_metadata(raw_audio)
    duration = frame_count / frame_rate if frame_rate else 0.0
    return AudioConversionResult(
        wav_bytes=raw_audio,
        sample_rate=frame_rate,
        channels=channels,
        duration_sec=duration,
    )


def _guess_audio_format(mime_type: str) -> str:
    if "webm" in mime_type:
        return "webm"
    if "ogg" in mime_type:
        return "ogg"
    if "mp3" in mime_type:
        return "mp3"
    if "wav" in mime_type:
        return "wav"
    return "webm"


def normalize_browser_audio(raw_audio: bytes, mime_type: str) -> AudioConversionResult:
    if not raw_audio:
        raise ValueError("Audio payload was empty.")

    if mime_type in {"audio/wav", "audio/x-wav"} or raw_audio[:4] == b"RIFF":
        return _passthrough_wav(raw_audio)

    try:
        process = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                _guess_audio_format(mime_type),
                "-i",
                "pipe:0",
                "-ac",
                str(TARGET_CHANNELS),
                "-ar",
                str(TARGET_SAMPLE_RATE),
                "-f",
                "wav",
                "pipe:1",
            ],
            input=raw_audio,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg is required for browser audio conversion but was not found on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(
            f"Audio conversion failed for mime type '{mime_type}': {stderr or 'ffmpeg decode error'}"
        ) from exc

    wav_bytes = process.stdout
    frame_rate, channels, frame_count = _read_wav_metadata(wav_bytes)

    return AudioConversionResult(
        wav_bytes=wav_bytes,
        sample_rate=frame_rate,
        channels=channels,
        duration_sec=(frame_count / frame_rate if frame_rate else 0.0),
    )
