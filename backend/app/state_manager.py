from __future__ import annotations

from copy import deepcopy

from app.models.intelligence import ActionItem, Decision, Risk
from app.models.memory import MemoryState
from app.models.utterance import Utterance


class StateManager:
    def __init__(self) -> None:
        self._states: dict[str, MemoryState] = {}

    def create(self, meeting_id: str) -> MemoryState:
        state = MemoryState(meeting_id=meeting_id)
        self._states[meeting_id] = state
        return state

    def get(self, meeting_id: str) -> MemoryState | None:
        return self._states.get(meeting_id)

    def append_chunk_transcript(
        self,
        meeting_id: str,
        chunk_id: int,
        display_utterances: list[Utterance],
        llm_utterances: list[Utterance],
        llm_window_chunks: int,
    ) -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")

        state.chunk_history.append(chunk_id)
        state.display_transcript_buffer.extend(display_utterances)
        state.llm_transcript_buffer.extend(llm_utterances)
        state.asr_chunks_since_last_llm += 1

        llm_window_ready = False
        current_window_utterances = len(state.llm_transcript_buffer)
        previous_window_utterances = len(state.previous_llm_window)

        if state.asr_chunks_since_last_llm >= llm_window_chunks:
            current_snapshot = [utterance.model_copy(deep=True) for utterance in state.llm_transcript_buffer]
            previous_snapshot = [utterance.model_copy(deep=True) for utterance in state.previous_llm_window]
            state.pending_previous_llm_window = previous_snapshot
            state.pending_current_llm_window = current_snapshot
            state.previous_llm_window = current_snapshot
            state.llm_transcript_buffer = []
            state.asr_chunks_since_last_llm = 0
            llm_window_ready = True
            current_window_utterances = len(current_snapshot)
            previous_window_utterances = len(previous_snapshot)

        return {
            "display_utterances": len(state.display_transcript_buffer),
            "llm_buffer_utterances": len(state.llm_transcript_buffer),
            "previous_window_utterances": previous_window_utterances,
            "asr_chunks_since_last_llm": state.asr_chunks_since_last_llm,
            "llm_window_ready": llm_window_ready,
            "current_window_utterances": current_window_utterances,
        }

    def consume_ready_llm_window(self, meeting_id: str) -> dict | None:
        state = self.get(meeting_id)
        if not state or not state.pending_current_llm_window:
            return None

        payload = {
            "previous_window": [utterance.model_copy(deep=True) for utterance in state.pending_previous_llm_window],
            "current_window": [utterance.model_copy(deep=True) for utterance in state.pending_current_llm_window],
            "queued_window": [utterance.model_copy(deep=True) for utterance in state.queued_llm_window],
        }
        state.pending_previous_llm_window = []
        state.pending_current_llm_window = []
        return payload

    def queue_failed_window(self, meeting_id: str, utterances: list[Utterance]) -> None:
        state = self.get(meeting_id)
        if not state:
            return
        state.queued_llm_window.extend([utterance.model_copy(deep=True) for utterance in utterances])
        state.consecutive_llm_failures += 1

    def clear_failed_window(self, meeting_id: str) -> None:
        state = self.get(meeting_id)
        if not state:
            return
        state.queued_llm_window = []
        state.consecutive_llm_failures = 0

    def apply_speaker_backfill(self, meeting_id: str, utterances: list[Utterance]) -> list[dict]:
        state = self.get(meeting_id)
        if not state:
            return []

        speaker_map = {utterance.id: utterance.speaker for utterance in utterances}
        updates: list[dict] = []

        for buffer_name in (
            "display_transcript_buffer",
            "llm_transcript_buffer",
            "previous_llm_window",
        ):
            buffer = getattr(state, buffer_name)
            for index, existing in enumerate(buffer):
                if existing.id not in speaker_map:
                    continue
                new_speaker = speaker_map[existing.id]
                buffer[index] = existing.model_copy(update={"speaker": new_speaker})

        for utterance in utterances:
            if utterance.speaker != "unknown" and utterance.speaker not in state.known_speakers:
                state.known_speakers.append(utterance.speaker)
            updates.append(
                {
                    "utterance_id": utterance.id,
                    "speaker": utterance.speaker,
                }
            )

        return updates

    def get_visible_items(self, meeting_id: str) -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        return {
            "summary": {
                "running_summary": state.running_summary,
                "current_topic_focus": state.current_topic_focus,
                "unresolved_issues": state.unresolved_issues,
                "locked": state.summary_human_locked,
            },
            "action_items": [item.model_dump(mode="json") for item in state.action_items if not item.deleted],
            "decisions": [item.model_dump(mode="json") for item in state.decisions if not item.deleted],
            "risks": [item.model_dump(mode="json") for item in state.risks if not item.deleted],
            "review_flags": list(state.review_flags),
        }

    def update_summary(self, meeting_id: str, summary: str) -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        state.running_summary = summary.strip()
        state.summary_human_locked = True
        return self.get_visible_items(meeting_id)

    def add_action_item(self, meeting_id: str, task: str, owner: str, deadline: str, priority: str, evidence: str) -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        item = ActionItem(
            id=f"manual-action-{len(state.action_items) + 1}",
            task=task.strip(),
            owner=owner.strip() or "unknown",
            deadline=deadline.strip() or "unspecified",
            priority=priority,
            status="pending",
            needs_review=False,
            evidence=evidence.strip(),
            chunk_origin=state.chunk_history[-1] if state.chunk_history else 0,
            human_locked=True,
        )
        state.action_items.append(item)
        return self.get_visible_items(meeting_id)

    def add_decision(self, meeting_id: str, decision_text: str, evidence: str = "") -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        item = Decision(
            id=f"manual-decision-{len(state.decisions) + 1}",
            decision=decision_text.strip(),
            evidence=evidence.strip(),
            chunk_origin=state.chunk_history[-1] if state.chunk_history else 0,
            human_locked=True,
        )
        state.decisions.append(item)
        return self.get_visible_items(meeting_id)

    def add_risk(self, meeting_id: str, risk_text: str, evidence: str = "") -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        item = Risk(
            id=f"manual-risk-{len(state.risks) + 1}",
            risk=risk_text.strip(),
            evidence=evidence.strip(),
            chunk_origin=state.chunk_history[-1] if state.chunk_history else 0,
            human_locked=True,
        )
        state.risks.append(item)
        return self.get_visible_items(meeting_id)

    def _resolve_collection(self, state: MemoryState, item_type: str):
        if item_type == "action_item":
            return state.action_items
        if item_type == "decision":
            return state.decisions
        if item_type == "risk":
            return state.risks
        raise ValueError(f"Unsupported item type: {item_type}")

    def update_item(self, meeting_id: str, item_type: str, item_id: str, updates: dict) -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        collection = self._resolve_collection(state, item_type)
        for index, item in enumerate(collection):
            if item.id != item_id:
                continue
            payload = deepcopy(item.model_dump(mode="json"))
            payload.update(updates)
            payload["human_locked"] = True
            collection[index] = item.__class__.model_validate(payload)
            return self.get_visible_items(meeting_id)
        raise ValueError(f"Item {item_id} not found in {item_type}.")

    def mark_item_deleted(self, meeting_id: str, item_type: str, item_id: str, deleted: bool) -> dict:
        state = self.get(meeting_id)
        if not state:
            raise ValueError(f"Meeting state not found for {meeting_id}.")
        collection = self._resolve_collection(state, item_type)
        for index, item in enumerate(collection):
            if item.id != item_id:
                continue
            collection[index] = item.model_copy(update={"deleted": deleted, "human_locked": True})
            return self.get_visible_items(meeting_id)
        raise ValueError(f"Item {item_id} not found in {item_type}.")

    def end(self, meeting_id: str) -> None:
        state = self._states.get(meeting_id)
        if state:
            state.is_active = False

    def remove(self, meeting_id: str) -> None:
        self._states.pop(meeting_id, None)


state_manager = StateManager()
