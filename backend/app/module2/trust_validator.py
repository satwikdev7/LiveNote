from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from difflib import SequenceMatcher

from pydantic import BaseModel, Field, ValidationError

from app.models.intelligence import ActionItem, Decision, EvidenceSpan, Risk
from app.models.memory import MemoryState
from app.models.utterance import Utterance


class SummaryResponse(BaseModel):
    running_summary: str = ""
    current_topic_focus: str = ""
    unresolved_issues: list[str] = Field(default_factory=list)


class ActionItemCandidate(BaseModel):
    task: str
    owner: str = "unknown"
    deadline: str = "unspecified"
    priority: str = "medium"
    status: str = "pending"
    needs_review: bool = False
    evidence: str
    evidence_spans: list[EvidenceSpan]


class ActionResponse(BaseModel):
    action_items: list[ActionItemCandidate] = Field(default_factory=list)


class DecisionCandidate(BaseModel):
    decision: str
    evidence: str
    evidence_spans: list[EvidenceSpan]


class DecisionResponse(BaseModel):
    decisions: list[DecisionCandidate] = Field(default_factory=list)


class RiskCandidate(BaseModel):
    risk: str
    evidence: str
    evidence_spans: list[EvidenceSpan]


class RiskResponse(BaseModel):
    risks: list[RiskCandidate] = Field(default_factory=list)


@dataclass
class TrustValidationResult:
    running_summary: str = ""
    current_topic_focus: str = ""
    unresolved_issues: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    trust_violations: list[dict] = field(default_factory=list)


class TrustValidator:
    def _normalize_evidence_spans(
        self,
        payload: dict,
        key: str,
        utterance_index: dict[str, Utterance],
    ) -> dict:
        items = payload.get(key, [])
        normalized_items = []

        for item in items:
            if not isinstance(item, dict):
                normalized_items.append(item)
                continue

            normalized_item = dict(item)
            evidence_spans = normalized_item.get("evidence_spans", [])
            normalized_spans = []

            for span in evidence_spans:
                if isinstance(span, str):
                    utterance = utterance_index.get(span)
                    if utterance:
                        normalized_spans.append(
                            {
                                "utterance_id": utterance.id,
                                "start_time": utterance.start_time,
                                "end_time": utterance.end_time,
                                "text": utterance.text,
                            }
                        )
                    continue

                if isinstance(span, dict):
                    span_copy = dict(span)
                    utterance_id = span_copy.get("utterance_id")
                    if utterance_id and utterance_id in utterance_index:
                        utterance = utterance_index[utterance_id]
                        span_copy.setdefault("start_time", utterance.start_time)
                        span_copy.setdefault("end_time", utterance.end_time)
                        span_copy.setdefault("text", utterance.text)
                    normalized_spans.append(span_copy)

            normalized_item["evidence_spans"] = normalized_spans
            normalized_items.append(normalized_item)

        normalized_payload = dict(payload)
        normalized_payload[key] = normalized_items
        return normalized_payload

    def _similar(self, left: str, right: str) -> float:
        return SequenceMatcher(None, left.lower().strip(), right.lower().strip()).ratio()

    def _add_violation(self, violations: list[dict], chunk_id: int, rule: str, item_type: str, detail: str) -> None:
        violations.append(
            {
                "rule": rule,
                "item_type": item_type,
                "chunk_id": chunk_id,
                "detail": detail,
            }
        )

    def _normalize_deadline(self, raw_deadline: str, meeting_started_at) -> tuple[str, str | None]:
        text = (raw_deadline or "unspecified").strip()
        if not text or text.lower() == "unspecified":
            return "unspecified", None
        lowered = text.lower()
        if meeting_started_at:
            if "tomorrow" in lowered:
                return text, (meeting_started_at + timedelta(days=1)).date().isoformat()
            if "today" in lowered:
                return text, meeting_started_at.date().isoformat()
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
        if match:
            return text, match.group(1)
        return "unspecified", None

    def _evidence_is_valid(self, evidence_spans: list[EvidenceSpan], utterance_index: dict[str, Utterance]) -> bool:
        if not evidence_spans:
            return False
        for span in evidence_spans:
            utterance = utterance_index.get(span.utterance_id or "")
            if not utterance:
                return False
            if span.start_time < utterance.start_time or span.end_time > utterance.end_time + 0.2:
                return False
        return True

    def validate(
        self,
        *,
        state: MemoryState,
        chunk_id: int,
        meeting_started_at,
        previous_window: list[Utterance],
        current_window: list[Utterance],
        summary_payload: dict,
        actions_payload: dict,
        decisions_payload: dict,
        risks_payload: dict,
    ) -> TrustValidationResult:
        utterance_index = {utterance.id: utterance for utterance in previous_window + current_window}
        result = TrustValidationResult()

        try:
            summary = SummaryResponse.model_validate(summary_payload)
            result.running_summary = summary.running_summary.strip()
            result.current_topic_focus = summary.current_topic_focus.strip()
            result.unresolved_issues = [issue.strip() for issue in summary.unresolved_issues if issue.strip()]
        except ValidationError as exc:
            self._add_violation(result.trust_violations, chunk_id, "JSON Validity", "summary", str(exc))

        actions_payload = self._normalize_evidence_spans(actions_payload, "action_items", utterance_index)
        decisions_payload = self._normalize_evidence_spans(decisions_payload, "decisions", utterance_index)
        risks_payload = self._normalize_evidence_spans(risks_payload, "risks", utterance_index)

        try:
            actions = ActionResponse.model_validate(actions_payload)
        except ValidationError as exc:
            actions = ActionResponse()
            self._add_violation(result.trust_violations, chunk_id, "JSON Validity", "action_item", str(exc))

        try:
            decisions = DecisionResponse.model_validate(decisions_payload)
        except ValidationError as exc:
            decisions = DecisionResponse()
            self._add_violation(result.trust_violations, chunk_id, "JSON Validity", "decision", str(exc))

        try:
            risks = RiskResponse.model_validate(risks_payload)
        except ValidationError as exc:
            risks = RiskResponse()
            self._add_violation(result.trust_violations, chunk_id, "JSON Validity", "risk", str(exc))

        commitment_pattern = re.compile(r"\b(i will|i'll|we will|we should|let's|please|handle|deploy|send|complete)\b", re.IGNORECASE)

        for index, candidate in enumerate(actions.action_items, start=1):
            if not self._evidence_is_valid(candidate.evidence_spans, utterance_index):
                self._add_violation(result.trust_violations, chunk_id, "Evidence Required", "action_item", candidate.task)
                continue
            if not commitment_pattern.search(candidate.evidence):
                self._add_violation(result.trust_violations, chunk_id, "Commitment-Language Check", "action_item", candidate.task)
                continue

            needs_review = candidate.needs_review
            owner = candidate.owner.strip() or "unknown"
            if owner != "unknown" and owner not in state.known_speakers:
                needs_review = True
                self._add_violation(result.trust_violations, chunk_id, "Owner Grounding", "action_item", candidate.task)

            deadline, normalized_deadline = self._normalize_deadline(candidate.deadline, meeting_started_at)
            if deadline == "unspecified" and candidate.deadline not in {"", "unspecified"}:
                needs_review = True
                self._add_violation(result.trust_violations, chunk_id, "Deadline Normalization", "action_item", candidate.task)

            duplicate = any(
                self._similar(candidate.task, existing.task) >= 0.85
                for existing in state.action_items + result.action_items
            )
            if duplicate:
                self._add_violation(result.trust_violations, chunk_id, "Duplicate Detection", "action_item", candidate.task)
                continue

            result.action_items.append(
                ActionItem(
                    id=f"action-{chunk_id}-{index}",
                    task=candidate.task.strip(),
                    owner=owner,
                    deadline=deadline,
                    normalized_deadline=normalized_deadline,
                    priority=candidate.priority,
                    status=candidate.status,
                    needs_review=needs_review,
                    evidence=candidate.evidence.strip(),
                    evidence_spans=candidate.evidence_spans,
                    chunk_origin=chunk_id,
                )
            )

        for index, candidate in enumerate(decisions.decisions, start=1):
            if not self._evidence_is_valid(candidate.evidence_spans, utterance_index):
                self._add_violation(result.trust_violations, chunk_id, "Evidence Required", "decision", candidate.decision)
                continue
            duplicate = any(
                self._similar(candidate.decision, existing.decision) >= 0.85
                for existing in state.decisions + result.decisions
            )
            if duplicate:
                self._add_violation(result.trust_violations, chunk_id, "Duplicate Detection", "decision", candidate.decision)
                continue
            result.decisions.append(
                Decision(
                    id=f"decision-{chunk_id}-{index}",
                    decision=candidate.decision.strip(),
                    evidence=candidate.evidence.strip(),
                    evidence_spans=candidate.evidence_spans,
                    chunk_origin=chunk_id,
                )
            )

        for index, candidate in enumerate(risks.risks, start=1):
            if not self._evidence_is_valid(candidate.evidence_spans, utterance_index):
                self._add_violation(result.trust_violations, chunk_id, "Evidence Required", "risk", candidate.risk)
                continue
            duplicate = any(
                self._similar(candidate.risk, existing.risk) >= 0.85
                for existing in state.risks + result.risks
            )
            if duplicate:
                self._add_violation(result.trust_violations, chunk_id, "Duplicate Detection", "risk", candidate.risk)
                continue
            result.risks.append(
                Risk(
                    id=f"risk-{chunk_id}-{index}",
                    risk=candidate.risk.strip(),
                    evidence=candidate.evidence.strip(),
                    evidence_spans=candidate.evidence_spans,
                    chunk_origin=chunk_id,
                )
            )

        result.review_flags = [violation["detail"] for violation in result.trust_violations]
        return result


trust_validator = TrustValidator()
