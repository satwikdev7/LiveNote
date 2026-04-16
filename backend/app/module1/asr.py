from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass

from app.config import settings
from app.models.utterance import Utterance


@dataclass
class ASRMetadata:
    model_info: str
    segment_count: int


class ASRService:
    def __init__(self, model_size: str | None = None) -> None:
        self._model_size = model_size or settings.whisper_model_size
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_wav_bytes(
        self,
        wav_bytes: bytes,
        chunk_id: int,
        chunk_offset_sec: float,
    ) -> tuple[list[Utterance], ASRMetadata]:
        model = self._get_model()

        with tempfile.NamedTemporaryFile(suffix=".wav") as temp_wav:
            temp_wav.write(wav_bytes)
            temp_wav.flush()
            segments, _info = model.transcribe(
                temp_wav.name,
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )

            utterances: list[Utterance] = []
            for index, segment in enumerate(segments, start=1):
                text = segment.text.strip()
                if not text:
                    continue

                avg_logprob = getattr(segment, "avg_logprob", -1.0)
                confidence = round(max(0.0, min(1.0, math.exp(avg_logprob))), 3)
                utterances.append(
                    Utterance(
                        id=f"chunk-{chunk_id}-utt-{index}",
                        chunk_id=chunk_id,
                        speaker="unknown",
                        text=text,
                        start_time=round(chunk_offset_sec + float(segment.start), 3),
                        end_time=round(chunk_offset_sec + float(segment.end), 3),
                        confidence=confidence,
                    )
                )

        return utterances, ASRMetadata(
            model_info=f"faster-whisper:{self._model_size}",
            segment_count=len(utterances),
        )


asr_service = ASRService()
