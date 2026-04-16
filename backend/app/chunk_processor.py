from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass

from app.config import settings
from app.module1.alignment import alignment_service, AlignmentService
from app.module1.asr import ASRService, asr_service
from app.module1.diarization import DiarizationService, diarization_service
from app.module1.noise_filter import NoiseFilterService, noise_filter_service
from app.schemas import ChunkUploadPayload
from app.session_manager import session_manager
from app.state_manager import state_manager
from app.utils.audio_utils import AudioConversionResult, normalize_browser_audio


@dataclass
class DiarizationContext:
    meeting_id: str
    chunk_id: int
    wav_bytes: bytes
    display_utterances: list
    chunk_offset_sec: float


@dataclass
class ProcessedChunkResult:
    transcript_payload: dict
    processing_payload: dict
    diarization_context: DiarizationContext | None


class ChunkProcessor:
    def __init__(
        self,
        asr: ASRService | None = None,
        diarizer: DiarizationService | None = None,
        alignment: AlignmentService | None = None,
        noise_filter: NoiseFilterService | None = None,
    ) -> None:
        self._asr = asr or asr_service
        self._diarizer = diarizer or diarization_service
        self._alignment = alignment or alignment_service
        self._noise_filter = noise_filter or noise_filter_service

    def decode_audio(self, audio_base64: str) -> bytes:
        return base64.b64decode(audio_base64)

    async def process_chunk(self, payload: ChunkUploadPayload) -> ProcessedChunkResult:
        started_at = time.perf_counter()
        raw_audio = self.decode_audio(payload.audio_base64)
        if not raw_audio:
            raise ValueError("Received an empty audio payload.")

        session_manager.register_chunk(
            meeting_id=payload.meeting_id,
            sequence_number=payload.sequence_number,
            chunk_size=len(raw_audio),
        )

        normalized_audio = await asyncio.to_thread(
            normalize_browser_audio,
            raw_audio,
            payload.mime_type,
        )
        chunk_offset_sec = float((payload.sequence_number - 1) * settings.asr_chunk_sec)
        utterances, metadata = await asyncio.to_thread(
            self._asr.transcribe_wav_bytes,
            normalized_audio.wav_bytes,
            payload.sequence_number,
            chunk_offset_sec,
        )
        display_utterances, llm_utterances = self._noise_filter.split_utterances(utterances)
        rolling_memory = state_manager.append_chunk_transcript(
            meeting_id=payload.meeting_id,
            chunk_id=payload.sequence_number,
            display_utterances=display_utterances,
            llm_utterances=llm_utterances,
            llm_window_chunks=settings.llm_window_chunks,
        )

        total_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
        transcript_payload = {
            "meeting_id": payload.meeting_id,
            "chunk_id": payload.sequence_number,
            "chunk_start_time": chunk_offset_sec,
            "chunk_end_time": round(chunk_offset_sec + normalized_audio.duration_sec, 3),
            "utterances": [utterance.model_dump(mode="json") for utterance in display_utterances],
            "diarization_pending": settings.diarization_enabled and bool(display_utterances),
            "rolling_memory": rolling_memory,
        }
        processing_payload = {
            "meeting_id": payload.meeting_id,
            "sequence_number": payload.sequence_number,
            "chunk_bytes": len(raw_audio),
            "mime_type": payload.mime_type,
            "duration_ms": payload.duration_ms,
            "processing_metadata": {
                "audio_duration_sec": round(normalized_audio.duration_sec, 3),
                "sample_rate": normalized_audio.sample_rate,
                "channels": normalized_audio.channels,
                "asr_time_ms": total_time_ms,
                "model_info": metadata.model_info,
                "segment_count": metadata.segment_count,
            },
        }

        diarization_context = None
        if settings.diarization_enabled and display_utterances:
            diarization_context = DiarizationContext(
                meeting_id=payload.meeting_id,
                chunk_id=payload.sequence_number,
                wav_bytes=normalized_audio.wav_bytes,
                display_utterances=display_utterances,
                chunk_offset_sec=chunk_offset_sec,
            )

        return ProcessedChunkResult(
            transcript_payload=transcript_payload,
            processing_payload=processing_payload,
            diarization_context=diarization_context,
        )

    async def process_diarization_backfill(self, context: DiarizationContext) -> dict | None:
        if not self._diarizer.is_enabled():
            return {
                "type": "ack",
                "payload": {
                    "message": (
                        f"Diarization skipped for chunk #{context.chunk_id}: missing Hugging Face token "
                        "or diarization disabled."
                    ),
                    "meeting_id": context.meeting_id,
                    "sequence_number": context.chunk_id,
                },
            }

        try:
            diarization_segments = await asyncio.to_thread(
                self._diarizer.diarize_wav_bytes,
                context.wav_bytes,
                context.chunk_offset_sec,
            )
            aligned = self._alignment.assign_speakers(context.display_utterances, diarization_segments)
            updates = state_manager.apply_speaker_backfill(context.meeting_id, aligned)
            if not updates:
                return None

            return {
                "type": "speaker_backfill",
                "payload": {
                    "meeting_id": context.meeting_id,
                    "chunk_id": context.chunk_id,
                    "updates": updates,
                    "known_speakers": state_manager.get(context.meeting_id).known_speakers
                    if state_manager.get(context.meeting_id)
                    else [],
                },
            }
        except Exception as exc:
            return {
                "type": "ack",
                "payload": {
                    "message": f"Diarization skipped for chunk #{context.chunk_id}: {exc}",
                    "meeting_id": context.meeting_id,
                    "sequence_number": context.chunk_id,
                },
            }


chunk_processor = ChunkProcessor()
