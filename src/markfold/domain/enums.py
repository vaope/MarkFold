from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    WEB = "web"
    CLI = "cli"
    FEISHU_MOBILE = "feishu_mobile"


class EventType(StrEnum):
    PROGRESS = "progress"
    TODO_CREATED = "todo_created"
    TODO_COMPLETED = "todo_completed"
    RISK = "risk"
    DECISION = "decision"
    NOTE = "note"


class ReviewStatus(StrEnum):
    AUTO_ACCEPTED = "auto_accepted"
    PENDING_REVIEW = "pending_review"
    CORRECTED = "corrected"


class ReviewItemStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class TodoStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


class WorkItemSource(StrEnum):
    IMPORT = "import"
    INIT = "init"
    AUTO = "auto"


class SyncJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class FeishuInboundStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    IGNORED = "ignored"
