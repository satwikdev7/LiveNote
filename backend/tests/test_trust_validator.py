from datetime import datetime, timezone

from app.models.memory import MemoryState
from app.models.utterance import Utterance
from app.module2.trust_validator import TrustValidator


def test_trust_validator_filters_ungrounded_action_without_commitment() -> None:
    validator = TrustValidator()
    state = MemoryState(meeting_id="meeting_test", known_speakers=["SPEAKER_00"])
    current_window = [
        Utterance(
            id="utt-1",
            chunk_id=1,
            speaker="SPEAKER_00",
            text="We discussed the issue briefly.",
            start_time=0.0,
            end_time=2.0,
            confidence=0.9,
        )
    ]

    result = validator.validate(
        state=state,
        chunk_id=1,
        meeting_started_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        previous_window=[],
        current_window=current_window,
        summary_payload={"running_summary": "Discussed the issue."},
        actions_payload={
            "action_items": [
                {
                    "task": "Discuss the issue",
                    "owner": "SPEAKER_99",
                    "deadline": "tomorrow",
                    "priority": "medium",
                    "status": "pending",
                    "needs_review": False,
                    "evidence": "We discussed the issue briefly.",
                    "evidence_spans": [
                        {
                            "utterance_id": "utt-1",
                            "start_time": 0.0,
                            "end_time": 2.0,
                            "text": "We discussed the issue briefly.",
                        }
                    ],
                }
            ]
        },
        decisions_payload={"decisions": []},
        risks_payload={"risks": []},
    )

    assert result.action_items == []
    assert any(violation["rule"] == "Commitment-Language Check" for violation in result.trust_violations)


def test_trust_validator_accepts_string_evidence_span_ids() -> None:
    validator = TrustValidator()
    state = MemoryState(meeting_id="meeting_test", known_speakers=["SPEAKER_00"])
    current_window = [
        Utterance(
            id="chunk-3-utt-3",
            chunk_id=3,
            speaker="SPEAKER_00",
            text="I will deploy the backend by tomorrow evening.",
            start_time=30.0,
            end_time=34.0,
            confidence=0.92,
        )
    ]

    result = validator.validate(
        state=state,
        chunk_id=4,
        meeting_started_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        previous_window=[],
        current_window=current_window,
        summary_payload={"running_summary": "Deployment discussed."},
        actions_payload={
            "action_items": [
                {
                    "task": "Deploy the backend by tomorrow evening.",
                    "owner": "SPEAKER_00",
                    "deadline": "tomorrow",
                    "priority": "high",
                    "status": "pending",
                    "needs_review": False,
                    "evidence": "I will deploy the backend by tomorrow evening.",
                    "evidence_spans": ["chunk-3-utt-3"],
                }
            ]
        },
        decisions_payload={"decisions": []},
        risks_payload={"risks": []},
    )

    assert len(result.action_items) == 1
    assert result.action_items[0].evidence_spans[0].utterance_id == "chunk-3-utt-3"
