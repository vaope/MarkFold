from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from markfold.repositories.database import Base


def make_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    title: Mapped[str] = mapped_column(String(255), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="active")
    source_type: Mapped[str] = mapped_column(String(50), default="init")
    markdown_doc_path: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text, default="")
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class InputEntry(Base):
    __tablename__ = "input_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    channel: Mapped[str] = mapped_column(String(50))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    linked_work_item_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(50), default="auto_accepted")
    context_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class StructuredEvent(Base):
    __tablename__ = "structured_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    work_item_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    source_input_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    work_item_id: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    file_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    source_input_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    linked_work_item_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    input_entry_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    candidate_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_work_item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    selected_work_item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChannelContext(Base):
    __tablename__ = "channel_contexts"

    context_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    active_work_item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class InitSession(Base):
    __tablename__ = "init_sessions"

    context_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    draft: Mapped[dict] = mapped_column(JSON, default=dict)
    last_assistant_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FeishuInboundMessage(Base):
    __tablename__ = "feishu_inbound_messages"

    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), index=True)
    chat_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sender_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    sender_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message_type: Mapped[str] = mapped_column(String(50))
    mentions: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentSyncJob(Base):
    __tablename__ = "document_sync_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=make_id)
    work_item_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(100), default="update")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
