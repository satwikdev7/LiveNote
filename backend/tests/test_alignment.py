from app.models.utterance import Utterance
from app.module1.alignment import AlignmentService
from app.module1.diarization import DiarizationSegment


def test_alignment_assigns_speaker_by_max_overlap() -> None:
    utterances = [
        Utterance(
            id="utt-1",
            chunk_id=1,
            speaker="unknown",
            text="We should ship Friday.",
            start_time=0.0,
            end_time=2.0,
            confidence=0.9,
        )
    ]
    diarization_segments = [
        DiarizationSegment(speaker="Speaker_1", start_time=0.0, end_time=0.8),
        DiarizationSegment(speaker="Speaker_2", start_time=0.8, end_time=2.2),
    ]

    aligned = AlignmentService().assign_speakers(utterances, diarization_segments)

    assert aligned[0].speaker == "Speaker_2"
