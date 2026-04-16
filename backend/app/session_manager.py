from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.models.memory import MemoryState
from app.schemas import MeetingMetadata
from app.state_manager import state_manager


@dataclass
class SessionRecord:
    meeting_id: str
    metadata: MeetingMetadata
    created_at: datetime
    is_active: bool = True
    last_chunk_sequence: int = 0
    received_chunks: int = 0
    chunk_sizes: list[int] = field(default_factory=list)


class SessionManager:
    def __init__(self) -> None:
        self._active_session: SessionRecord | None = None

    def create_session(self, metadata: MeetingMetadata) -> tuple[SessionRecord, MemoryState]:
        if self._active_session and self._active_session.is_active:
            raise ValueError("A meeting session is already active on this backend instance.")

        meeting_id = f"meeting_{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)
        session = SessionRecord(
            meeting_id=meeting_id,
            metadata=metadata,
            created_at=created_at,
        )
        self._active_session = session
        memory_state = state_manager.create(meeting_id)
        return session, memory_state

    def get_session(self, meeting_id: str | None = None) -> SessionRecord | None:
        if not self._active_session:
            return None
        if meeting_id is None or self._active_session.meeting_id == meeting_id:
            return self._active_session
        return None

    def register_chunk(self, meeting_id: str, sequence_number: int, chunk_size: int) -> SessionRecord:
        session = self.get_session(meeting_id)
        if not session or not session.is_active:
            raise ValueError("No active meeting session found for this chunk.")

        if sequence_number <= session.last_chunk_sequence:
            raise ValueError("Chunk sequence number must increase monotonically.")

        session.last_chunk_sequence = sequence_number
        session.received_chunks += 1
        session.chunk_sizes.append(chunk_size)
        return session

    def end_session(self, meeting_id: str) -> SessionRecord:
        session = self.get_session(meeting_id)
        if not session or not session.is_active:
            raise ValueError("No active meeting session found to end.")

        session.is_active = False
        state_manager.end(meeting_id)
        return session

    def snapshot(self) -> dict:
        if not self._active_session:
            return {
                "meetingId": None,
                "active": False,
                "mode": None,
                "startedAt": None,
                "lastChunkSequence": 0,
                "receivedChunks": 0,
            }

        return {
            "meetingId": self._active_session.meeting_id,
            "active": self._active_session.is_active,
            "mode": self._active_session.metadata.mode,
            "startedAt": self._active_session.created_at.isoformat(),
            "lastChunkSequence": self._active_session.last_chunk_sequence,
            "receivedChunks": self._active_session.received_chunks,
        }


session_manager = SessionManager()
