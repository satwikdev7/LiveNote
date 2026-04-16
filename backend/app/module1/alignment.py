from __future__ import annotations

from app.models.utterance import Utterance
from app.module1.diarization import DiarizationSegment


class AlignmentService:
    @staticmethod
    def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
        return max(0.0, min(end_a, end_b) - max(start_a, start_b))

    def assign_speakers(
        self,
        utterances: list[Utterance],
        speaker_segments: list[DiarizationSegment],
    ) -> list[Utterance]:
        aligned: list[Utterance] = []

        for utterance in utterances:
            best_speaker = utterance.speaker
            best_overlap = 0.0

            for segment in speaker_segments:
                overlap = self._overlap(
                    utterance.start_time,
                    utterance.end_time,
                    segment.start_time,
                    segment.end_time,
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = segment.speaker

            aligned.append(utterance.model_copy(update={"speaker": best_speaker}))

        return aligned


alignment_service = AlignmentService()
