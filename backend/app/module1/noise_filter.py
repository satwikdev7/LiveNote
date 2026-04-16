from __future__ import annotations

import re

from app.models.utterance import Utterance


FILLER_PATTERN = re.compile(r"\b(um+|uh+|hmm+|like|you know|sort of|kind of)\b", re.IGNORECASE)
MULTISPACE_PATTERN = re.compile(r"\s+")


class NoiseFilterService:
    def _normalize_display_text(self, text: str) -> str:
        return MULTISPACE_PATTERN.sub(" ", text).strip()

    def _normalize_llm_text(self, text: str) -> str:
        stripped = FILLER_PATTERN.sub("", text)
        return MULTISPACE_PATTERN.sub(" ", stripped).strip(" ,.")

    def split_utterances(self, utterances: list[Utterance]) -> tuple[list[Utterance], list[Utterance]]:
        display_utterances: list[Utterance] = []
        llm_utterances: list[Utterance] = []

        for utterance in utterances:
            display_text = self._normalize_display_text(utterance.text)
            if not display_text:
                continue

            display_utterance = utterance.model_copy(update={"text": display_text})
            display_utterances.append(display_utterance)

            llm_text = self._normalize_llm_text(display_text)
            if len(llm_text) < 3:
                continue

            if llm_text.lower() in {"yes", "yeah", "okay", "ok", "right"}:
                continue

            llm_utterances.append(display_utterance.model_copy(update={"text": llm_text}))

        return display_utterances, llm_utterances


noise_filter_service = NoiseFilterService()
