from __future__ import annotations

import asyncio
import base64
import io
import wave

from app.chunk_processor import ChunkProcessor
from app.models.utterance import Utterance
from app.schemas import ChunkUploadPayload, MeetingMetadata
from app.session_manager import session_manager
from app.state_manager import state_manager


def build_wav_bytes(duration_sec: float = 0.25, sample_rate: int = 16_000) -> bytes:
    frame_count = int(duration_sec * sample_rate)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return output.getvalue()


class FakeASRService:
    def transcribe_wav_bytes(self, wav_bytes: bytes, chunk_id: int, chunk_offset_sec: float):
        return (
            [
                Utterance(
                    id=f"chunk-{chunk_id}-utt-1",
                    chunk_id=chunk_id,
                    speaker="unknown",
                    text="um we should finalize the deck by Friday",
                    start_time=chunk_offset_sec + 0.1,
                    end_time=chunk_offset_sec + 1.8,
                    confidence=0.93,
                )
            ],
            type("Meta", (), {"model_info": "fake-asr", "segment_count": 1})(),
        )


class FakeDiarizationService:
    def is_enabled(self) -> bool:
        return False


def test_chunk_processor_generates_transcript_payload() -> None:
    session, _memory = session_manager.create_session(
        MeetingMetadata(title="Processor Test", mode="live")
    )
    wav_bytes = build_wav_bytes()
    payload = ChunkUploadPayload(
        meeting_id=session.meeting_id,
        sequence_number=1,
        mime_type="audio/wav",
        audio_base64=base64.b64encode(wav_bytes).decode("utf-8"),
        captured_at="2026-04-15T17:00:00Z",
        duration_ms=15_000,
    )
    processor = ChunkProcessor(asr=FakeASRService(), diarizer=FakeDiarizationService())

    result = asyncio.run(processor.process_chunk(payload))

    assert result.transcript_payload["utterances"][0]["text"] == "um we should finalize the deck by Friday"
    assert result.transcript_payload["rolling_memory"]["llm_window_ready"] is False
    assert state_manager.get(session.meeting_id) is not None
    session_manager.end_session(session.meeting_id)
