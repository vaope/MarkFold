from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from markfold.domain.enums import Channel, EventType, ReviewItemStatus, ReviewStatus, TodoStatus


class ExtractedEvent(BaseModel):
    type: EventType
    content: str


class WorkItemCandidate(BaseModel):
    id: str
    title: str
    aliases: list[str] = Field(default_factory=list)
    open_todos: list[str] = Field(default_factory=list)


class WorkItemChoice(BaseModel):
    work_item_id: str | None = None
    confidence: float = 0.0
    reason: str = ""


class InitDraft(BaseModel):
    title: str | None = None
    status: str | None = "active"
    goal: str | None = None
    background: str | None = None
    aliases: list[str] = Field(default_factory=list)
    progress_summary: str | None = None
    todos: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InitTurnResult(BaseModel):
    draft: InitDraft = Field(default_factory=InitDraft)
    assistant_message: str
    ready_to_create: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class InputSubmissionResult(BaseModel):
    outcome: str
    message: str
    work_item_id: str | None = None
    review_id: str | None = None
    events: list[ExtractedEvent] = Field(default_factory=list)


class WorkItemView(BaseModel):
    id: str
    title: str
    status: str
    source_type: str
    markdown_doc_path: str
    goal: str
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime

    @classmethod
    def from_model(cls, model: Any) -> "WorkItemView":
        return cls.model_validate(model, from_attributes=True)


class TodoView(BaseModel):
    id: str
    work_item_id: str
    content: str
    status: TodoStatus
    created_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def from_model(cls, model: Any) -> "TodoView":
        return cls.model_validate(model, from_attributes=True)


class ReviewView(BaseModel):
    id: str
    input_entry_id: str
    status: ReviewItemStatus
    candidate_ids: list[str] = Field(default_factory=list)
    suggested_work_item_id: str | None = None
    selected_work_item_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    @classmethod
    def from_model(cls, model: Any) -> "ReviewView":
        return cls.model_validate(model, from_attributes=True)


class DailySummaryItem(BaseModel):
    work_item_id: str
    title: str
    progress: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ImportWorkItemRequest(BaseModel):
    path: str
    context_key: str | None = "cli:default"


class InitCommandRequest(BaseModel):
    title: str | None = None
    goal: str | None = ""
    status: str | None = "active"
    context_key: str | None = "cli:default"


class UseCommandRequest(BaseModel):
    title: str
    context_key: str | None = "cli:default"


class TodoCommandRequest(BaseModel):
    content: str
    context_key: str | None = "cli:default"


class DoneCommandRequest(BaseModel):
    content: str
    context_key: str | None = "cli:default"


class InputRequest(BaseModel):
    raw_text: str = ""
    channel: Channel = Channel.CLI
    context_key: str | None = "cli:default"
    work_item_id: str | None = None


class ReviewResolveRequest(BaseModel):
    work_item_id: str
    notes: str | None = None


class QueryRequest(BaseModel):
    target_date: dt_date | None = None


class StatusResponse(BaseModel):
    work_item: WorkItemView
    open_todos: list[TodoView] = Field(default_factory=list)
    recent_events: list[ExtractedEvent] = Field(default_factory=list)


class ApiMessage(BaseModel):
    message: str


class InputEntryView(BaseModel):
    id: str
    channel: Channel
    raw_text: str
    linked_work_item_id: str | None = None
    confidence: float
    review_status: ReviewStatus
    created_at: datetime

    @classmethod
    def from_model(cls, model: Any) -> "InputEntryView":
        return cls.model_validate(model, from_attributes=True)
