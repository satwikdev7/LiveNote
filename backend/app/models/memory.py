from __future__ import annotations

from dataclasses import dataclass, field

from app.models.intelligence import ActionItem, Decision, Risk
from app.models.utterance import Utterance


@dataclass
class MemoryState:
    meeting_id: str
    running_summary: str = ""
    current_topic_focus: str = ""
    unresolved_issues: list[str] = field(default_factory=list)
    summary_human_locked: bool = False
    action_items: list[ActionItem] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    known_speakers: list[str] = field(default_factory=list)
    chunk_history: list[int] = field(default_factory=list)
    display_transcript_buffer: list[Utterance] = field(default_factory=list)
    llm_transcript_buffer: list[Utterance] = field(default_factory=list)
    previous_llm_window: list[Utterance] = field(default_factory=list)
    pending_previous_llm_window: list[Utterance] = field(default_factory=list)
    pending_current_llm_window: list[Utterance] = field(default_factory=list)
    queued_llm_window: list[Utterance] = field(default_factory=list)
    consecutive_llm_failures: int = 0
    final_report: dict | None = None
    asr_chunks_since_last_llm: int = 0
    is_active: bool = True
