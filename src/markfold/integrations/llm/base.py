from __future__ import annotations

from typing import Protocol

from markfold.domain.schemas import ExtractedEvent, InitDraft, InitTurnResult, WorkItemCandidate, WorkItemChoice


class LlmProvider(Protocol):
    def extract_events(self, raw_text: str) -> list[ExtractedEvent]:
        ...

    def choose_work_item(
        self, raw_text: str, candidates: list[WorkItemCandidate]
    ) -> WorkItemChoice:
        ...

    def advance_init_session(self, latest_user_message: str, draft: InitDraft) -> InitTurnResult:
        ...
