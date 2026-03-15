from __future__ import annotations

import re
from datetime import date, datetime, time, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from markfold.repositories.models import (
    Attachment,
    ChannelContext,
    DocumentSyncJob,
    FeishuInboundMessage,
    InitSession,
    InputEntry,
    ReviewItem,
    StructuredEvent,
    Todo,
    WorkItem,
    utcnow,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


class Store:
    def __init__(self, session: Session):
        self.session = session

    def create_work_item(
        self,
        *,
        title: str,
        markdown_doc_path: str,
        source_type: str,
        status: str = "active",
        goal: str = "",
        aliases: list[str] | None = None,
    ) -> WorkItem:
        item = WorkItem(
            title=title.strip(),
            markdown_doc_path=markdown_doc_path,
            source_type=source_type,
            status=status,
            goal=goal.strip(),
            aliases=aliases or [],
        )
        self.session.add(item)
        self.session.flush()
        return item

    def list_work_items(self) -> list[WorkItem]:
        stmt = select(WorkItem).order_by(WorkItem.updated_at.desc())
        return list(self.session.scalars(stmt))

    def get_work_item(self, work_item_id: str) -> WorkItem | None:
        return self.session.get(WorkItem, work_item_id)

    def find_work_item_by_title(self, title: str) -> WorkItem | None:
        normalized = _normalize(title)
        items = self.list_work_items()
        for item in items:
            if _normalize(item.title) == normalized:
                return item
            aliases = [_normalize(alias) for alias in item.aliases or []]
            if normalized in aliases:
                return item
        for item in items:
            haystacks = [_normalize(item.title), *[_normalize(alias) for alias in item.aliases or []]]
            if any(normalized in haystack for haystack in haystacks):
                return item
        return None

    def touch_work_item(self, work_item_id: str) -> None:
        item = self.get_work_item(work_item_id)
        if item is None:
            return
        item.last_activity_at = utcnow()
        item.updated_at = utcnow()
        self.session.add(item)

    def create_input_entry(
        self,
        *,
        channel: str,
        raw_text: str,
        context_key: str | None,
    ) -> InputEntry:
        entry = InputEntry(channel=channel, raw_text=raw_text, context_key=context_key)
        self.session.add(entry)
        self.session.flush()
        return entry

    def get_input_entry(self, input_entry_id: str) -> InputEntry | None:
        return self.session.get(InputEntry, input_entry_id)

    def update_input_entry(
        self,
        input_entry: InputEntry,
        *,
        linked_work_item_id: str | None = None,
        confidence: float | None = None,
        review_status: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> InputEntry:
        if linked_work_item_id is not None:
            input_entry.linked_work_item_id = linked_work_item_id
        if confidence is not None:
            input_entry.confidence = confidence
        if review_status is not None:
            input_entry.review_status = review_status
        if attachment_ids is not None:
            input_entry.attachment_ids = attachment_ids
        self.session.add(input_entry)
        self.session.flush()
        return input_entry

    def create_attachment(
        self,
        *,
        file_path: str,
        file_type: str,
        original_filename: str,
        source_input_id: str | None,
        linked_work_item_id: str | None = None,
    ) -> Attachment:
        attachment = Attachment(
            file_path=file_path,
            file_type=file_type,
            original_filename=original_filename,
            source_input_id=source_input_id,
            linked_work_item_id=linked_work_item_id,
        )
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def set_attachments_work_item(self, attachment_ids: list[str], work_item_id: str) -> None:
        for attachment_id in attachment_ids:
            attachment = self.session.get(Attachment, attachment_id)
            if attachment is None:
                continue
            attachment.linked_work_item_id = work_item_id
            self.session.add(attachment)

    def list_attachments_for_work_item(self, work_item_id: str) -> list[Attachment]:
        stmt = select(Attachment).where(Attachment.linked_work_item_id == work_item_id)
        stmt = stmt.order_by(Attachment.created_at.asc())
        return list(self.session.scalars(stmt))

    def create_event(
        self,
        *,
        work_item_id: str,
        event_type: str,
        content: str,
        source_input_id: str | None = None,
    ) -> StructuredEvent:
        event = StructuredEvent(
            work_item_id=work_item_id,
            type=event_type,
            content=content.strip(),
            source_input_id=source_input_id,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_recent_events(self, work_item_id: str, limit: int = 20) -> list[StructuredEvent]:
        stmt = (
            select(StructuredEvent)
            .where(StructuredEvent.work_item_id == work_item_id)
            .order_by(StructuredEvent.happened_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_events_for_work_item(self, work_item_id: str) -> list[StructuredEvent]:
        stmt = select(StructuredEvent).where(StructuredEvent.work_item_id == work_item_id)
        stmt = stmt.order_by(StructuredEvent.happened_at.asc())
        return list(self.session.scalars(stmt))

    def list_events_for_date(self, target_date: date) -> list[StructuredEvent]:
        start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
        stmt = select(StructuredEvent).where(StructuredEvent.happened_at.between(start, end))
        stmt = stmt.order_by(StructuredEvent.happened_at.asc())
        return list(self.session.scalars(stmt))

    def create_todo(
        self,
        *,
        work_item_id: str,
        content: str,
        status: str = "open",
        source_channel: str | None = None,
        source_event_id: str | None = None,
    ) -> Todo:
        todo = Todo(
            work_item_id=work_item_id,
            content=content.strip(),
            status=status,
            source_channel=source_channel,
            source_event_id=source_event_id,
            completed_at=utcnow() if status == "done" else None,
        )
        self.session.add(todo)
        self.session.flush()
        return todo

    def list_open_todos(self, work_item_id: str | None = None) -> list[Todo]:
        stmt: Select[tuple[Todo]] = select(Todo).where(Todo.status == "open")
        if work_item_id is not None:
            stmt = stmt.where(Todo.work_item_id == work_item_id)
        stmt = stmt.order_by(Todo.created_at.asc())
        return list(self.session.scalars(stmt))

    def list_done_todos(self, work_item_id: str) -> list[Todo]:
        stmt = select(Todo).where(Todo.work_item_id == work_item_id, Todo.status == "done")
        stmt = stmt.order_by(Todo.completed_at.asc())
        return list(self.session.scalars(stmt))

    def find_open_todo_match(self, work_item_id: str, content: str) -> Todo | None:
        normalized_target = _normalize(content)
        todos = self.list_open_todos(work_item_id)
        for todo in todos:
            normalized_todo = _normalize(todo.content)
            if normalized_todo == normalized_target:
                return todo
        for todo in todos:
            normalized_todo = _normalize(todo.content)
            if normalized_target in normalized_todo or normalized_todo in normalized_target:
                return todo
        return None

    def mark_todo_done(self, todo: Todo) -> Todo:
        todo.status = "done"
        todo.completed_at = utcnow()
        self.session.add(todo)
        self.session.flush()
        return todo

    def set_context(self, context_key: str, work_item_id: str | None) -> ChannelContext:
        context = self.get_context(context_key)
        if context is None:
            context = ChannelContext(context_key=context_key, active_work_item_id=work_item_id)
        else:
            context.active_work_item_id = work_item_id
            context.updated_at = utcnow()
        self.session.add(context)
        self.session.flush()
        return context

    def get_context(self, context_key: str) -> ChannelContext | None:
        return self.session.get(ChannelContext, context_key)

    def get_init_session(self, context_key: str) -> InitSession | None:
        return self.session.get(InitSession, context_key)

    def upsert_init_session(
        self,
        *,
        context_key: str,
        draft: dict,
        last_assistant_message: str,
        status: str = "active",
    ) -> InitSession:
        session = self.get_init_session(context_key)
        if session is None:
            session = InitSession(
                context_key=context_key,
                draft=draft,
                last_assistant_message=last_assistant_message,
                status=status,
            )
        else:
            session.draft = draft
            session.last_assistant_message = last_assistant_message
            session.status = status
            session.updated_at = utcnow()
        self.session.add(session)
        self.session.flush()
        return session

    def delete_init_session(self, context_key: str) -> None:
        session = self.get_init_session(context_key)
        if session is None:
            return
        self.session.delete(session)
        self.session.flush()

    def get_feishu_inbound_message(self, message_id: str) -> FeishuInboundMessage | None:
        return self.session.get(FeishuInboundMessage, message_id)

    def create_feishu_inbound_message(
        self,
        *,
        message_id: str,
        chat_id: str,
        chat_type: str | None,
        sender_id: str | None,
        sender_type: str | None,
        message_type: str,
        mentions: list[str],
        payload: dict,
        status: str,
        last_error: str | None = None,
    ) -> FeishuInboundMessage:
        message = FeishuInboundMessage(
            message_id=message_id,
            chat_id=chat_id,
            chat_type=chat_type,
            sender_id=sender_id,
            sender_type=sender_type,
            message_type=message_type,
            mentions=mentions,
            payload=payload,
            status=status,
            last_error=last_error,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def update_feishu_inbound_message(
        self,
        message: FeishuInboundMessage,
        *,
        status: str | None = None,
        attempts: int | None = None,
        last_error: str | None = None,
        processed_at: datetime | None = None,
    ) -> FeishuInboundMessage:
        if status is not None:
            message.status = status
        if attempts is not None:
            message.attempts = attempts
        if last_error is not None or (last_error is None and status is not None):
            message.last_error = last_error
        if processed_at is not None:
            message.processed_at = processed_at
        message.updated_at = utcnow()
        self.session.add(message)
        self.session.flush()
        return message

    def list_feishu_inbound_messages_by_status(
        self,
        statuses: list[str],
        *,
        max_attempts: int | None = None,
        limit: int = 100,
    ) -> list[FeishuInboundMessage]:
        stmt = select(FeishuInboundMessage).where(FeishuInboundMessage.status.in_(statuses))
        if max_attempts is not None:
            stmt = stmt.where(FeishuInboundMessage.attempts < max_attempts)
        stmt = stmt.order_by(FeishuInboundMessage.created_at.asc()).limit(limit)
        return list(self.session.scalars(stmt))

    def create_review_item(
        self,
        *,
        input_entry_id: str,
        payload: dict,
        candidate_ids: list[str],
        suggested_work_item_id: str | None,
        notes: str | None = None,
    ) -> ReviewItem:
        review = ReviewItem(
            input_entry_id=input_entry_id,
            payload=payload,
            candidate_ids=candidate_ids,
            suggested_work_item_id=suggested_work_item_id,
            notes=notes,
        )
        self.session.add(review)
        self.session.flush()
        return review

    def list_reviews(self, status: str = "pending") -> list[ReviewItem]:
        stmt = select(ReviewItem)
        if status:
            stmt = stmt.where(ReviewItem.status == status)
        stmt = stmt.order_by(ReviewItem.created_at.asc())
        return list(self.session.scalars(stmt))

    def get_review_item(self, review_id: str) -> ReviewItem | None:
        return self.session.get(ReviewItem, review_id)

    def enqueue_sync_job(self, *, work_item_id: str, reason: str = "update") -> DocumentSyncJob:
        job = DocumentSyncJob(work_item_id=work_item_id, reason=reason)
        self.session.add(job)
        self.session.flush()
        return job

    def list_pending_sync_jobs(self, limit: int = 20) -> list[DocumentSyncJob]:
        stmt = select(DocumentSyncJob).where(DocumentSyncJob.status.in_(["pending", "failed"]))
        stmt = stmt.order_by(DocumentSyncJob.created_at.asc()).limit(limit)
        return list(self.session.scalars(stmt))

    def get_sync_job(self, job_id: str) -> DocumentSyncJob | None:
        return self.session.get(DocumentSyncJob, job_id)
