from __future__ import annotations

from copy import deepcopy

from app.module2.deepseek_client import DeepSeekClient, deepseek_client
from app.module2.memory_manager import MemoryManager, memory_manager
from app.module2.prompt_builder import PromptBuilder
from app.module2.trust_validator import TrustValidator, trust_validator
from app.session_manager import session_manager
from app.state_manager import state_manager
from app.utils.export_utils import build_json_export, encode_export_payload
from app.utils.supabase_utils import supabase_persistence


class IntelligenceExtractor:
    def __init__(
        self,
        client: DeepSeekClient | None = None,
        validator: TrustValidator | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._client = client or deepseek_client
        self._validator = validator or trust_validator
        self._memory = memory or memory_manager

    def build_live_payload(self, meeting_id: str, chunk_id: int, provider: str, model: str) -> dict:
        state = self._memory.get_state(meeting_id)
        visible = state_manager.get_visible_items(meeting_id)
        return {
            "meeting_id": meeting_id,
            "chunk_id": chunk_id,
            "summary": visible["summary"],
            "action_items": visible["action_items"],
            "decisions": visible["decisions"],
            "risks": visible["risks"],
            "review_flags": visible["review_flags"],
            "llm_metadata": {
                "provider": provider,
                "model": model,
                "queued_windows": len(state.queued_llm_window),
            },
        }

    def build_state_sync_payload(self, meeting_id: str) -> dict:
        state = self._memory.get_state(meeting_id)
        return {
            "transcript": [utterance.model_dump(mode="json") for utterance in state.display_transcript_buffer],
            "rolling_memory": {
                "display_utterances": len(state.display_transcript_buffer),
                "llm_buffer_utterances": len(state.llm_transcript_buffer),
                "previous_window_utterances": len(state.previous_llm_window),
                "asr_chunks_since_last_llm": state.asr_chunks_since_last_llm,
                "llm_window_ready": bool(state.pending_current_llm_window),
                "current_window_utterances": len(state.pending_current_llm_window or state.llm_transcript_buffer),
            },
            "intelligence": self.build_live_payload(
                meeting_id=meeting_id,
                chunk_id=state.chunk_history[-1] if state.chunk_history else 0,
                provider="deepseek" if self._client.get_client() is not None else "heuristic-fallback",
                model="deepseek-chat" if self._client.get_client() is not None else "heuristic",
            ),
            "final_report": deepcopy(state.final_report),
        }

    async def process_ready_window(self, meeting_id: str, chunk_id: int) -> list[dict]:
        state = self._memory.get_state(meeting_id)
        windows = state_manager.consume_ready_llm_window(meeting_id)
        if not windows:
            return []

        previous_window = windows["queued_window"] + windows["previous_window"]
        current_window = windows["current_window"]
        if not current_window:
            return []

        session = session_manager.get_session(meeting_id)
        builder = PromptBuilder(meeting_started_at=session.created_at if session else None)

        try:
            summary_payload = self._client.complete_json(
                task_name="summary",
                system_prompt=builder.build_summary_prompts(state, previous_window, current_window)[0],
                user_prompt=builder.build_summary_prompts(state, previous_window, current_window)[1],
                heuristic_fallback=lambda: self._client.heuristic_summary(current_window, previous_window),
            )
            actions_payload = self._client.complete_json(
                task_name="action_items",
                system_prompt=builder.build_action_prompts(state, previous_window, current_window)[0],
                user_prompt=builder.build_action_prompts(state, previous_window, current_window)[1],
                heuristic_fallback=lambda: self._client.heuristic_actions(current_window),
            )
            decisions_payload = self._client.complete_json(
                task_name="decisions",
                system_prompt=builder.build_decision_prompts(state, previous_window, current_window)[0],
                user_prompt=builder.build_decision_prompts(state, previous_window, current_window)[1],
                heuristic_fallback=lambda: self._client.heuristic_decisions(current_window),
            )
            risks_payload = self._client.complete_json(
                task_name="risks",
                system_prompt=builder.build_risk_prompts(state, previous_window, current_window)[0],
                user_prompt=builder.build_risk_prompts(state, previous_window, current_window)[1],
                heuristic_fallback=lambda: self._client.heuristic_risks(current_window),
            )
        except Exception as exc:
            state_manager.queue_failed_window(meeting_id, current_window)
            state = self._memory.get_state(meeting_id)
            messages = [
                {
                    "type": "trust_violation",
                    "payload": {
                        "meeting_id": meeting_id,
                        "chunk_id": chunk_id,
                        "rule": "LLM Failure Handling",
                        "item_type": "intelligence_cycle",
                        "detail": str(exc),
                    },
                }
            ]
            if state.consecutive_llm_failures >= 3:
                messages.append(
                    {
                        "type": "trust_violation",
                        "payload": {
                            "meeting_id": meeting_id,
                            "chunk_id": chunk_id,
                            "rule": "LLM Failure Handling",
                            "item_type": "intelligence_cycle",
                            "detail": "Intelligence temporarily unavailable. The current window has been queued for merge into the next cycle.",
                        },
                    }
                )
            return messages

        validated = self._validator.validate(
            state=state,
            chunk_id=chunk_id,
            meeting_started_at=session.created_at if session else None,
            previous_window=previous_window,
            current_window=current_window,
            summary_payload=summary_payload,
            actions_payload=actions_payload,
            decisions_payload=decisions_payload,
            risks_payload=risks_payload,
        )
        merged_state = self._memory.merge_validated_result(meeting_id, validated)
        state_manager.clear_failed_window(meeting_id)

        messages = [
            {
                "type": "trust_violation",
                "payload": {
                    "meeting_id": meeting_id,
                    "chunk_id": violation["chunk_id"],
                    "rule": violation["rule"],
                    "item_type": violation["item_type"],
                    "detail": violation["detail"],
                },
            }
            for violation in validated.trust_violations
        ]
        messages.append(
            {
                "type": "intelligence_update",
                "payload": self.build_live_payload(
                    meeting_id=meeting_id,
                    chunk_id=chunk_id,
                    provider="deepseek" if self._client.get_client() is not None else "heuristic-fallback",
                    model="deepseek-chat" if self._client.get_client() is not None else "heuristic",
                ),
            }
        )
        return messages

    async def finalize_meeting(self, meeting_id: str) -> list[dict]:
        state = self._memory.get_state(meeting_id)
        session = session_manager.get_session(meeting_id)
        chunk_id = state.chunk_history[-1] if state.chunk_history else 0

        if state.llm_transcript_buffer:
            builder = PromptBuilder(meeting_started_at=session.created_at if session else None)
            previous_window = [utterance.model_copy(deep=True) for utterance in state.previous_llm_window]
            current_window = [utterance.model_copy(deep=True) for utterance in state.llm_transcript_buffer]
            try:
                summary_payload = self._client.complete_json(
                    task_name="summary",
                    system_prompt=builder.build_summary_prompts(state, previous_window, current_window)[0],
                    user_prompt=builder.build_summary_prompts(state, previous_window, current_window)[1],
                    heuristic_fallback=lambda: self._client.heuristic_summary(current_window, previous_window),
                )
                actions_payload = self._client.complete_json(
                    task_name="action_items",
                    system_prompt=builder.build_action_prompts(state, previous_window, current_window)[0],
                    user_prompt=builder.build_action_prompts(state, previous_window, current_window)[1],
                    heuristic_fallback=lambda: self._client.heuristic_actions(current_window),
                )
                decisions_payload = self._client.complete_json(
                    task_name="decisions",
                    system_prompt=builder.build_decision_prompts(state, previous_window, current_window)[0],
                    user_prompt=builder.build_decision_prompts(state, previous_window, current_window)[1],
                    heuristic_fallback=lambda: self._client.heuristic_decisions(current_window),
                )
                risks_payload = self._client.complete_json(
                    task_name="risks",
                    system_prompt=builder.build_risk_prompts(state, previous_window, current_window)[0],
                    user_prompt=builder.build_risk_prompts(state, previous_window, current_window)[1],
                    heuristic_fallback=lambda: self._client.heuristic_risks(current_window),
                )
                validated = self._validator.validate(
                    state=state,
                    chunk_id=chunk_id,
                    meeting_started_at=session.created_at if session else None,
                    previous_window=previous_window,
                    current_window=current_window,
                    summary_payload=summary_payload,
                    actions_payload=actions_payload,
                    decisions_payload=decisions_payload,
                    risks_payload=risks_payload,
                )
                self._memory.merge_validated_result(meeting_id, validated)
            except Exception:
                pass

        report = build_json_export(state, session)
        exports = encode_export_payload(report)
        storage = supabase_persistence.persist_report(report, exports)
        state.final_report = {
            **exports,
            "storage": storage,
        }

        messages = [
            {
                "type": "intelligence_update",
                "payload": self.build_live_payload(
                    meeting_id=meeting_id,
                    chunk_id=chunk_id,
                    provider="deepseek" if self._client.get_client() is not None else "heuristic-fallback",
                    model="deepseek-chat" if self._client.get_client() is not None else "heuristic",
                ),
            },
            {
                "type": "consolidation_complete",
                "payload": {
                    "meeting_id": meeting_id,
                    "report": report,
                    "json_base64": exports["json_base64"],
                    "pdf_base64": exports["pdf_base64"],
                    "storage": storage,
                },
            },
        ]
        return messages


intelligence_extractor = IntelligenceExtractor()
