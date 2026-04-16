from __future__ import annotations

import json
from datetime import datetime

from app.models.memory import MemoryState
from app.models.utterance import Utterance


def _serialize_utterances(utterances: list[Utterance]) -> list[dict]:
    return [
        {
            "utterance_id": utterance.id,
            "speaker": utterance.speaker,
            "start_time": utterance.start_time,
            "end_time": utterance.end_time,
            "text": utterance.text,
        }
        for utterance in utterances
    ]


class PromptBuilder:
    def __init__(self, meeting_started_at: datetime | None = None) -> None:
        self._meeting_started_at = meeting_started_at

    def _common_context(
        self,
        state: MemoryState,
        previous_window: list[Utterance],
        current_window: list[Utterance],
    ) -> str:
        payload = {
            "meeting_id": state.meeting_id,
            "meeting_started_at": self._meeting_started_at.isoformat() if self._meeting_started_at else None,
            "known_speakers": state.known_speakers,
            "running_summary": state.running_summary,
            "current_topic_focus": state.current_topic_focus,
            "unresolved_issues": state.unresolved_issues,
            "existing_action_items": [item.model_dump(mode="json") for item in state.action_items],
            "existing_decisions": [item.model_dump(mode="json") for item in state.decisions],
            "existing_risks": [item.model_dump(mode="json") for item in state.risks],
            "previous_window": _serialize_utterances(previous_window),
            "current_window": _serialize_utterances(current_window),
        }
        return json.dumps(payload, ensure_ascii=True)

    def build_summary_prompts(
        self,
        state: MemoryState,
        previous_window: list[Utterance],
        current_window: list[Utterance],
    ) -> tuple[str, str]:
        system = (
            "You update a running meeting summary. Return only JSON with keys "
            "`running_summary`, `current_topic_focus`, and `unresolved_issues`."
        )
        return system, self._common_context(state, previous_window, current_window)

    def build_action_prompts(
        self,
        state: MemoryState,
        previous_window: list[Utterance],
        current_window: list[Utterance],
    ) -> tuple[str, str]:
        system = (
            "Extract action items from the meeting transcript. Return only JSON with key "
            "`action_items`, where each item has `task`, `owner`, `deadline`, `priority`, "
            "`status`, `needs_review`, `evidence`, and `evidence_spans`."
        )
        return system, self._common_context(state, previous_window, current_window)

    def build_decision_prompts(
        self,
        state: MemoryState,
        previous_window: list[Utterance],
        current_window: list[Utterance],
    ) -> tuple[str, str]:
        system = (
            "Extract meeting decisions. Return only JSON with key `decisions`, where each item has "
            "`decision`, `evidence`, and `evidence_spans`."
        )
        return system, self._common_context(state, previous_window, current_window)

    def build_risk_prompts(
        self,
        state: MemoryState,
        previous_window: list[Utterance],
        current_window: list[Utterance],
    ) -> tuple[str, str]:
        system = (
            "Extract risks or blockers. Return only JSON with key `risks`, where each item has "
            "`risk`, `evidence`, and `evidence_spans`."
        )
        return system, self._common_context(state, previous_window, current_window)
