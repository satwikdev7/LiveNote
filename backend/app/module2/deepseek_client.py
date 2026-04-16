from __future__ import annotations

import json
import re
from collections.abc import Callable

from app.config import settings
from app.models.utterance import Utterance


def _extract_json(content: str) -> dict:
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value).strip()
        value = re.sub(r"```$", "", value).strip()
    return json.loads(value)


class DeepSeekClient:
    def __init__(self) -> None:
        self._client = None

    def get_client(self):
        if self._client is not None:
            return self._client

        if not settings.deepseek_api_key:
            return None

        from openai import OpenAI

        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        return self._client

    def complete_json(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        heuristic_fallback: Callable[[], dict],
    ) -> dict:
        client = self.get_client()
        if client is None:
            return heuristic_fallback()

        last_error: Exception | None = None
        for _ in range(settings.llm_max_retries):
            try:
                response = client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=False,
                    response_format={"type": "json_object"},
                )
                return _extract_json(response.choices[0].message.content or "{}")
            except Exception as exc:  # pragma: no cover - API path
                last_error = exc

        error_text = str(last_error or "")
        if "Insufficient Balance" in error_text or "Error code: 402" in error_text:
            return heuristic_fallback()

        raise RuntimeError(f"DeepSeek {task_name} failed after retries: {last_error}")

    def heuristic_summary(self, current_window: list[Utterance], previous_window: list[Utterance]) -> dict:
        utterances = previous_window[-2:] + current_window[-4:]
        combined = " ".join(utterance.text for utterance in utterances).strip()
        return {
            "running_summary": combined[:500] if combined else "Meeting discussion is in progress.",
            "current_topic_focus": current_window[-1].text[:120] if current_window else "",
            "unresolved_issues": [],
        }

    def heuristic_actions(self, current_window: list[Utterance]) -> dict:
        commitment_tokens = ("i will", "i'll", "we will", "we should", "let's", "please", "deploy", "send", "complete", "handle")
        items = []
        for utterance in current_window:
            lowered = utterance.text.lower()
            if not any(token in lowered for token in commitment_tokens):
                continue
            items.append(
                {
                    "task": utterance.text,
                    "owner": utterance.speaker,
                    "deadline": "unspecified",
                    "priority": "medium",
                    "status": "pending",
                    "needs_review": utterance.speaker == "unknown",
                    "evidence": utterance.text,
                    "evidence_spans": [
                        {
                            "utterance_id": utterance.id,
                            "start_time": utterance.start_time,
                            "end_time": utterance.end_time,
                            "text": utterance.text,
                        }
                    ],
                }
            )
        return {"action_items": items[:5]}

    def heuristic_decisions(self, current_window: list[Utterance]) -> dict:
        items = []
        for utterance in current_window:
            lowered = utterance.text.lower()
            if not any(token in lowered for token in ("decision", "agreed", "we will", "let's make that")):
                continue
            items.append(
                {
                    "decision": utterance.text,
                    "evidence": utterance.text,
                    "evidence_spans": [
                        {
                            "utterance_id": utterance.id,
                            "start_time": utterance.start_time,
                            "end_time": utterance.end_time,
                            "text": utterance.text,
                        }
                    ],
                }
            )
        return {"decisions": items[:5]}

    def heuristic_risks(self, current_window: list[Utterance]) -> dict:
        items = []
        for utterance in current_window:
            lowered = utterance.text.lower()
            if not any(token in lowered for token in ("risk", "concern", "blocker", "latency", "slower", "problem")):
                continue
            items.append(
                {
                    "risk": utterance.text,
                    "evidence": utterance.text,
                    "evidence_spans": [
                        {
                            "utterance_id": utterance.id,
                            "start_time": utterance.start_time,
                            "end_time": utterance.end_time,
                            "text": utterance.text,
                        }
                    ],
                }
            )
        return {"risks": items[:5]}


deepseek_client = DeepSeekClient()
