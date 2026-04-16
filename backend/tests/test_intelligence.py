from datetime import timezone, datetime

from app.models.utterance import Utterance
from app.module2.intelligence_extractor import IntelligenceExtractor
from app.schemas import MeetingMetadata
from app.session_manager import session_manager
from app.state_manager import state_manager


class FakeClient:
    def get_client(self):
        return None

    def complete_json(self, *, heuristic_fallback, **kwargs):
        return heuristic_fallback()

    def heuristic_summary(self, current_window, previous_window):
        return {
            "running_summary": "Team aligned on deploying the backend and preparing the poster.",
            "current_topic_focus": "Deployment plan",
            "unresolved_issues": ["Confirm cloud latency"],
        }

    def heuristic_actions(self, current_window):
        utterance = current_window[0]
        return {
            "action_items": [
                {
                    "task": "Deploy the backend by tomorrow evening.",
                    "owner": utterance.speaker,
                    "deadline": "tomorrow",
                    "priority": "high",
                    "status": "pending",
                    "needs_review": False,
                    "evidence": "I will deploy the backend by tomorrow evening.",
                    "evidence_spans": [
                        {
                            "utterance_id": utterance.id,
                            "start_time": utterance.start_time,
                            "end_time": utterance.end_time,
                            "text": utterance.text,
                        }
                    ],
                }
            ]
        }

    def heuristic_decisions(self, current_window):
        utterance = current_window[-1]
        return {
            "decisions": [
                {
                    "decision": "Use transcript-only mode if latency is too high.",
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
            ]
        }

    def heuristic_risks(self, current_window):
        utterance = current_window[-1]
        return {
            "risks": [
                {
                    "risk": "Cloud latency may be too high for the public demo.",
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
            ]
        }


def test_intelligence_extractor_emits_validated_update() -> None:
    session, state = session_manager.create_session(MeetingMetadata(title="Intelligence Test", mode="live"))
    state.known_speakers = ["SPEAKER_00"]

    llm_utterances = [
        Utterance(
            id="utt-1",
            chunk_id=1,
            speaker="SPEAKER_00",
            text="I will deploy the backend by tomorrow evening.",
            start_time=0.0,
            end_time=3.0,
            confidence=0.9,
        ),
        Utterance(
            id="utt-2",
            chunk_id=1,
            speaker="SPEAKER_00",
            text="If latency is too high, we will switch the public demo to transcript only mode.",
            start_time=3.1,
            end_time=7.0,
            confidence=0.9,
        ),
    ]

    state_manager.append_chunk_transcript(
        meeting_id=session.meeting_id,
        chunk_id=1,
        display_utterances=llm_utterances,
        llm_utterances=llm_utterances,
        llm_window_chunks=1,
    )

    extractor = IntelligenceExtractor(client=FakeClient())
    messages = __import__("asyncio").run(extractor.process_ready_window(session.meeting_id, 1))

    intelligence_messages = [message for message in messages if message["type"] == "intelligence_update"]
    assert len(intelligence_messages) == 1
    payload = intelligence_messages[0]["payload"]
    assert payload["summary"]["running_summary"]
    assert payload["action_items"]
    assert payload["decisions"]
    assert payload["risks"]

    session_manager.end_session(session.meeting_id)
    state_manager.remove(session.meeting_id)
