from __future__ import annotations

import re

from app.models.memory import MemoryState
from app.module2.trust_validator import TrustValidationResult
from app.state_manager import state_manager


class MemoryManager:
    @staticmethod
    def _fingerprint(*parts: str) -> str:
        return re.sub(r"\s+", " ", " ".join(parts).strip().lower())

    def get_state(self, meeting_id: str) -> MemoryState:
        state = state_manager.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        return state

    def merge_validated_result(self, meeting_id: str, validated: TrustValidationResult) -> MemoryState:
        state = self.get_state(meeting_id)

        if not state.summary_human_locked and validated.running_summary:
            state.running_summary = validated.running_summary
            state.current_topic_focus = validated.current_topic_focus
            state.unresolved_issues = validated.unresolved_issues

        existing_actions = {
            self._fingerprint(item.owner, item.task): item
            for item in state.action_items
            if not item.deleted
        }
        for item in validated.action_items:
            key = self._fingerprint(item.owner, item.task)
            if key in existing_actions:
                continue
            state.action_items.append(item)
            existing_actions[key] = item

        existing_decisions = {
            self._fingerprint(item.decision): item
            for item in state.decisions
            if not item.deleted
        }
        for item in validated.decisions:
            key = self._fingerprint(item.decision)
            if key in existing_decisions:
                continue
            state.decisions.append(item)
            existing_decisions[key] = item

        existing_risks = {
            self._fingerprint(item.risk): item
            for item in state.risks
            if not item.deleted
        }
        for item in validated.risks:
            key = self._fingerprint(item.risk)
            if key in existing_risks:
                continue
            state.risks.append(item)
            existing_risks[key] = item

        state.review_flags = validated.review_flags
        return state


memory_manager = MemoryManager()
