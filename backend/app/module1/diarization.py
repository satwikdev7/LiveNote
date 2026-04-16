from __future__ import annotations

import inspect
import os
import tempfile
from dataclasses import dataclass
from types import SimpleNamespace

from app.config import settings


@dataclass
class DiarizationSegment:
    speaker: str
    start_time: float
    end_time: float


class DiarizationService:
    def __init__(self) -> None:
        self._pipeline = None

    def is_enabled(self) -> bool:
        return settings.diarization_enabled and bool(settings.huggingface_token)

    def _get_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        if not self.is_enabled():
            raise RuntimeError("Diarization is disabled or Hugging Face token is missing.")

        try:
            os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
            os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

            import torch
            import torchaudio
            import huggingface_hub
            import soundfile as sf

            if "weights_only" in inspect.signature(torch.load).parameters:
                original_torch_load = torch.load

                def _torch_load_compat(*args, **kwargs):
                    kwargs.setdefault("weights_only", False)
                    return original_torch_load(*args, **kwargs)

                torch.load = _torch_load_compat

            try:
                torch.serialization.add_safe_globals([torch.torch_version.TorchVersion])
            except Exception:
                pass

            if not hasattr(torchaudio, "AudioMetaData"):
                class _AudioMetaData(SimpleNamespace):  # pragma: no cover - compatibility shim
                    sample_rate: int
                    num_frames: int
                    num_channels: int
                    bits_per_sample: int
                    encoding: str

                torchaudio.AudioMetaData = _AudioMetaData

            if not hasattr(torchaudio, "list_audio_backends"):
                torchaudio.list_audio_backends = lambda: ["soundfile"]

            if not hasattr(torchaudio, "info"):
                def _info(audio, backend=None):
                    metadata = sf.info(audio)
                    subtype = metadata.subtype_info or metadata.subtype or "UNKNOWN"
                    return torchaudio.AudioMetaData(
                        sample_rate=int(metadata.samplerate),
                        num_frames=int(metadata.frames),
                        num_channels=int(metadata.channels),
                        bits_per_sample=0,
                        encoding=str(subtype),
                    )

                torchaudio.info = _info

            def _load(audio, frame_offset=0, num_frames=-1, normalize=True, channels_first=True, format=None, buffer_size=4096, backend=None):
                start_frame = 0 if frame_offset is None else int(frame_offset)
                frame_count = -1 if num_frames is None else int(num_frames)
                waveform, sample_rate = sf.read(
                    audio,
                    start=start_frame,
                    frames=frame_count,
                    dtype="float32",
                    always_2d=True,
                )
                tensor = torch.from_numpy(waveform.T)
                if not channels_first:
                    tensor = tensor.transpose(0, 1)
                return tensor, int(sample_rate)

            torchaudio.load = _load

            if "use_auth_token" not in inspect.signature(huggingface_hub.hf_hub_download).parameters:
                original_download = huggingface_hub.hf_hub_download

                def _hf_hub_download_compat(*args, use_auth_token=None, **kwargs):
                    if use_auth_token is not None and "token" not in kwargs:
                        kwargs["token"] = use_auth_token
                    return original_download(*args, **kwargs)

                huggingface_hub.hf_hub_download = _hf_hub_download_compat

            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise RuntimeError(
                "pyannote.audio is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=settings.huggingface_token,
        )
        return self._pipeline

    def diarize_wav_bytes(self, wav_bytes: bytes, chunk_offset_sec: float) -> list[DiarizationSegment]:
        pipeline = self._get_pipeline()

        with tempfile.NamedTemporaryFile(suffix=".wav") as temp_wav:
            temp_wav.write(wav_bytes)
            temp_wav.flush()
            diarization = pipeline(temp_wav.name)

        segments: list[DiarizationSegment] = []
        for turn, _track, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                DiarizationSegment(
                    speaker=str(speaker),
                    start_time=round(chunk_offset_sec + float(turn.start), 3),
                    end_time=round(chunk_offset_sec + float(turn.end), 3),
                )
            )
        return segments


diarization_service = DiarizationService()
