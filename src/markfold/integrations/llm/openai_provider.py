from __future__ import annotations

import json

from openai import OpenAI

from markfold.domain.schemas import ExtractedEvent, InitDraft, InitTurnResult, WorkItemCandidate, WorkItemChoice


class OpenAILlmProvider:
    def __init__(self, *, api_key: str, base_url: str | None = None, model: str | None = None):
        self.client = OpenAI(api_key=api_key, base_url=base_url or None)
        self.model = model or "gpt-4.1-mini"

    def extract_events(self, raw_text: str) -> list[ExtractedEvent]:
        prompt = (
            "Extract structured work log events. Return JSON with key 'events'. "
            "Each event must have 'type' and 'content'. Allowed types: "
            "progress, todo_created, todo_completed, risk, decision, note."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": raw_text},
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return [ExtractedEvent.model_validate(item) for item in payload.get("events", [])]

    def choose_work_item(
        self, raw_text: str, candidates: list[WorkItemCandidate]
    ) -> WorkItemChoice:
        candidate_payload = [candidate.model_dump() for candidate in candidates]
        prompt = (
            "Choose the most likely work item for the input. Return JSON with "
            "work_item_id, confidence between 0 and 1, and reason. If unsure, "
            "set work_item_id to null."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps({"raw_text": raw_text, "candidates": candidate_payload}),
                },
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return WorkItemChoice.model_validate(payload)

    def advance_init_session(self, latest_user_message: str, draft: InitDraft) -> InitTurnResult:
        prompt = (
            "You are helping a user initialize a work-item markdown document through progressive chat. "
            "Update the draft from the latest user message, decide what is still missing, and ask the next best question in Chinese. "
            "Return JSON with keys: draft, assistant_message, ready_to_create, missing_fields. "
            "Keep assistant_message concise, helpful, and specific. "
            "The draft fields are: title, status, goal, background, aliases, progress_summary, todos, risks, notes. "
            "Only set ready_to_create=true when the draft is good enough to create a useful first document."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "latest_user_message": latest_user_message,
                            "draft": draft.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return InitTurnResult.model_validate(payload)
