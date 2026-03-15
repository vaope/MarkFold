from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from markfold.config import Settings, get_settings
from markfold.domain.enums import Channel, EventType, ReviewItemStatus, ReviewStatus, TodoStatus, WorkItemSource
from markfold.domain.schemas import (
    ExtractedEvent,
    InitDraft,
    InputSubmissionResult,
    ReviewView,
    StatusResponse,
    TodoView,
    WorkItemView,
)
from markfold.integrations.llm.base import LlmProvider
from markfold.integrations.llm.factory import get_llm_provider
from markfold.repositories.models import utcnow
from markfold.repositories.store import Store
from markfold.services.command_parser import ParsedCommand, parse_command
from markfold.services.identification import identify_work_item
from markfold.services.queries import daily_summary as build_daily_summary
from markfold.services.queries import work_item_status
from markfold.services.sync import process_pending_jobs, sync_work_item_now


INIT_BACKGROUND_PREFIX = "[init_background] "


@dataclass
class UploadedAttachment:
    filename: str
    content_type: str
    content: bytes


def _safe_filename(name: str) -> str:
    stripped = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return stripped or "attachment.bin"


def _document_filename(prefix: str = "work-item") -> str:
    return f"{prefix}-{utcnow().strftime('%Y%m%d-%H%M%S-%f')}.md"


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def _extract_todos(content: str) -> tuple[list[str], list[str]]:
    open_todos: list[str] = []
    done_todos: list[str] = []
    for line in content.splitlines():
        if line.strip().startswith("- [ ]"):
            open_todos.append(line.split("]", 1)[1].strip())
        elif line.strip().startswith("- [x]"):
            done_todos.append(line.split("]", 1)[1].strip())
    return open_todos, done_todos


class MarkFoldService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        llm_provider: LlmProvider | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.store = Store(session)
        self._llm_provider = llm_provider

    def list_work_items(self) -> list[WorkItemView]:
        return [WorkItemView.from_model(item) for item in self.store.list_work_items()]

    def list_open_todos(self, work_item_id: str | None = None) -> list[TodoView]:
        return [TodoView.from_model(todo) for todo in self.store.list_open_todos(work_item_id)]

    def list_reviews(self) -> list[ReviewView]:
        return [ReviewView.from_model(review) for review in self.store.list_reviews()]

    def create_work_item(
        self,
        *,
        title: str,
        goal: str = "",
        status: str = "active",
        context_key: str | None = "cli:default",
        source_type: WorkItemSource = WorkItemSource.INIT,
        aliases: list[str] | None = None,
    ) -> WorkItemView:
        document_path = self.settings.work_items_dir / _document_filename()
        work_item = self.store.create_work_item(
            title=title,
            markdown_doc_path=str(document_path.resolve()),
            source_type=source_type,
            status=status,
            goal=goal,
            aliases=aliases,
        )
        if context_key:
            self.store.set_context(context_key, work_item.id)
        self.session.commit()
        sync_work_item_now(self.session, work_item.id, settings=self.settings)
        self.session.commit()
        return WorkItemView.from_model(work_item)

    def import_work_item(self, path: str, context_key: str | None = "cli:default") -> WorkItemView:
        source_path = Path(path).expanduser()
        if not source_path.is_absolute():
            source_path = Path.cwd() / source_path
        if not source_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {source_path}")
        content = source_path.read_text(encoding="utf-8")
        title = _extract_title(content, source_path.stem)
        open_todos, done_todos = _extract_todos(content)
        work_item = self.store.create_work_item(
            title=title,
            markdown_doc_path=str(source_path.resolve()),
            source_type=WorkItemSource.IMPORT,
            status="active",
        )
        for todo in open_todos:
            self.store.create_todo(work_item_id=work_item.id, content=todo, status=TodoStatus.OPEN)
        for todo in done_todos:
            self.store.create_todo(work_item_id=work_item.id, content=todo, status=TodoStatus.DONE)
        if context_key:
            self.store.set_context(context_key, work_item.id)
        self.store.enqueue_sync_job(work_item_id=work_item.id, reason="import")
        self.session.commit()
        process_pending_jobs(self.session, settings=self.settings)
        return WorkItemView.from_model(work_item)

    def use_work_item(self, title: str, context_key: str = "cli:default") -> WorkItemView:
        work_item = self.store.find_work_item_by_title(title)
        if work_item is None:
            raise ValueError(f"Unknown work item: {title}")
        self.store.set_context(context_key, work_item.id)
        self.session.commit()
        return WorkItemView.from_model(work_item)

    def add_explicit_todo(
        self,
        content: str,
        context_key: str = "cli:default",
        *,
        source_input_id: str | None = None,
        channel: Channel = Channel.CLI,
    ) -> InputSubmissionResult:
        work_item = self._require_context_work_item(context_key)
        event = self.store.create_event(
            work_item_id=work_item.id,
            event_type=EventType.TODO_CREATED,
            content=content,
            source_input_id=source_input_id,
        )
        self.store.create_todo(
            work_item_id=work_item.id,
            content=content,
            status=TodoStatus.OPEN,
            source_channel=channel,
            source_event_id=event.id,
        )
        if source_input_id:
            input_entry = self.store.get_input_entry(source_input_id)
            if input_entry is not None:
                self.store.update_input_entry(input_entry, linked_work_item_id=work_item.id, confidence=1.0)
        self.store.touch_work_item(work_item.id)
        self.store.enqueue_sync_job(work_item_id=work_item.id, reason="explicit_todo")
        self.session.commit()
        process_pending_jobs(self.session, settings=self.settings)
        return InputSubmissionResult(
            outcome="accepted",
            message=f"Added todo to {work_item.title}",
            work_item_id=work_item.id,
            events=[ExtractedEvent(type=EventType.TODO_CREATED, content=content)],
        )

    def mark_todo_done(
        self,
        content: str,
        context_key: str = "cli:default",
        *,
        source_input_id: str | None = None,
    ) -> InputSubmissionResult:
        work_item = self._require_context_work_item(context_key)
        matched = self.store.find_open_todo_match(work_item.id, content)
        self.store.create_event(
            work_item_id=work_item.id,
            event_type=EventType.TODO_COMPLETED,
            content=content,
            source_input_id=source_input_id,
        )
        if matched is not None:
            self.store.mark_todo_done(matched)
        if source_input_id:
            input_entry = self.store.get_input_entry(source_input_id)
            if input_entry is not None:
                self.store.update_input_entry(input_entry, linked_work_item_id=work_item.id, confidence=1.0)
        self.store.touch_work_item(work_item.id)
        self.store.enqueue_sync_job(work_item_id=work_item.id, reason="todo_done")
        self.session.commit()
        process_pending_jobs(self.session, settings=self.settings)
        return InputSubmissionResult(
            outcome="accepted",
            message=f"Marked todo as done in {work_item.title}",
            work_item_id=work_item.id,
            events=[ExtractedEvent(type=EventType.TODO_COMPLETED, content=content)],
        )

    def handle_input(
        self,
        *,
        raw_text: str,
        channel: Channel,
        context_key: str | None,
        uploaded_attachments: Iterable[UploadedAttachment] | None = None,
        explicit_work_item_id: str | None = None,
    ) -> InputSubmissionResult:
        uploaded_attachments = list(uploaded_attachments or [])
        input_entry = self.store.create_input_entry(channel=channel, raw_text=raw_text, context_key=context_key)

        attachment_ids = self._persist_attachments(input_entry.id, uploaded_attachments)
        self.store.update_input_entry(input_entry, attachment_ids=attachment_ids)

        command = parse_command(raw_text)
        if command is not None:
            return self._handle_command(command, context_key, input_entry.id, channel)

        if context_key:
            init_session = self.store.get_init_session(context_key)
            if init_session is not None and init_session.status == "active":
                return self._advance_init_session(
                    context_key=context_key,
                    latest_user_message=raw_text,
                )

        events = self.llm_provider.extract_events(raw_text) if raw_text.strip() else []
        if raw_text.strip() and not events:
            raise ValueError("LLM 没有返回任何结构化事件，请检查模型配置或提示词输出。")
        if not events and attachment_ids:
            events = [ExtractedEvent(type=EventType.NOTE, content=f"Uploaded {len(attachment_ids)} attachment(s)")]

        if explicit_work_item_id:
            choice_work_item_id = explicit_work_item_id
            confidence = 1.0
            candidate_ids = [explicit_work_item_id]
        else:
            choice, candidate_ids = identify_work_item(
                store=self.store,
                raw_text=raw_text,
                context_key=context_key,
                llm_provider=self.llm_provider,
            )
            choice_work_item_id = choice.work_item_id
            confidence = choice.confidence

        if not choice_work_item_id or confidence < 0.55:
            self.store.update_input_entry(
                input_entry,
                confidence=confidence,
                review_status=ReviewStatus.PENDING_REVIEW,
            )
            review = self.store.create_review_item(
                input_entry_id=input_entry.id,
                payload={
                    "raw_text": raw_text,
                    "channel": channel,
                    "context_key": context_key,
                    "events": [event.model_dump() for event in events],
                    "attachment_ids": attachment_ids,
                },
                candidate_ids=candidate_ids,
                suggested_work_item_id=choice_work_item_id,
                notes="Low confidence work item binding",
            )
            self.session.commit()
            return InputSubmissionResult(
                outcome="pending_review",
                message="Input saved but needs review before it can be attached to a work item.",
                review_id=review.id,
                events=events,
            )

        work_item = self.store.get_work_item(choice_work_item_id)
        if work_item is None:
            raise ValueError("Chosen work item no longer exists")

        self.store.update_input_entry(
            input_entry,
            linked_work_item_id=work_item.id,
            confidence=confidence,
            review_status=ReviewStatus.AUTO_ACCEPTED,
        )
        if context_key:
            self.store.set_context(context_key, work_item.id)
        if attachment_ids:
            self.store.set_attachments_work_item(attachment_ids, work_item.id)
        self._materialize_events(
            work_item_id=work_item.id,
            source_input_id=input_entry.id,
            channel=channel,
            events=events,
        )
        self.store.touch_work_item(work_item.id)
        self.store.enqueue_sync_job(work_item_id=work_item.id, reason="input")
        self.session.commit()
        process_pending_jobs(self.session, settings=self.settings)
        message = f"Archived to {work_item.title}"
        if confidence < 0.8:
            message += " (medium confidence)"
        return InputSubmissionResult(
            outcome="accepted",
            message=message,
            work_item_id=work_item.id,
            events=events,
        )

    def resolve_review(self, review_id: str, work_item_id: str, notes: str | None = None) -> ReviewView:
        review = self.store.get_review_item(review_id)
        if review is None:
            raise ValueError("review not found")
        if review.status != ReviewItemStatus.PENDING:
            raise ValueError("review already resolved")

        payload = review.payload or {}
        input_entry = self.store.get_input_entry(review.input_entry_id)
        if input_entry is None:
            raise ValueError("input entry not found for review")

        events = [ExtractedEvent.model_validate(item) for item in payload.get("events", [])]
        attachment_ids = payload.get("attachment_ids", [])
        channel = payload.get("channel", Channel.CLI)
        self.store.update_input_entry(
            input_entry,
            linked_work_item_id=work_item_id,
            confidence=1.0,
            review_status=ReviewStatus.CORRECTED,
        )
        self.store.set_attachments_work_item(attachment_ids, work_item_id)
        self._materialize_events(
            work_item_id=work_item_id,
            source_input_id=input_entry.id,
            channel=Channel(channel),
            events=events,
        )
        self.store.touch_work_item(work_item_id)
        review.status = ReviewItemStatus.RESOLVED
        review.selected_work_item_id = work_item_id
        review.notes = notes or review.notes
        review.resolved_at = utcnow()
        self.session.add(review)
        self.store.enqueue_sync_job(work_item_id=work_item_id, reason="review_resolution")
        self.session.commit()
        process_pending_jobs(self.session, settings=self.settings)
        return ReviewView.from_model(review)

    def status(self, title_or_id: str | None = None, context_key: str | None = "cli:default") -> StatusResponse:
        return work_item_status(self.store, title_or_id, context_key=context_key)

    def daily_summary(self, target_date=None):
        return build_daily_summary(self.store, target_date)

    def run_worker(self, limit: int = 20) -> int:
        return process_pending_jobs(self.session, settings=self.settings, limit=limit)

    def start_init_session(
        self,
        *,
        context_key: str,
        seed_title: str | None = None,
        seed_goal: str | None = None,
        seed_status: str | None = None,
    ) -> InputSubmissionResult:
        draft = InitDraft(
            title=seed_title or None,
            goal=seed_goal or None,
            status=seed_status or "active",
        )
        kickoff_message = "用户想开始初始化一个新的工作项。"
        if seed_title:
            kickoff_message += f" 当前已知标题是：{seed_title}。"
        turn = self.llm_provider.advance_init_session(kickoff_message, draft)
        self.store.upsert_init_session(
            context_key=context_key,
            draft=turn.draft.model_dump(),
            last_assistant_message=turn.assistant_message,
            status="active",
        )
        self.session.commit()
        return InputSubmissionResult(
            outcome="init_in_progress",
            message=turn.assistant_message,
        )

    def cancel_init_session(self, context_key: str) -> InputSubmissionResult:
        session = self.store.get_init_session(context_key)
        if session is None or session.status != "active":
            raise ValueError("当前没有进行中的初始化会话。")
        self.store.delete_init_session(context_key)
        self.session.commit()
        return InputSubmissionResult(
            outcome="accepted",
            message="已取消当前初始化会话。",
        )

    def finish_init_session(self, context_key: str) -> InputSubmissionResult:
        session = self.store.get_init_session(context_key)
        if session is None or session.status != "active":
            raise ValueError("当前没有进行中的初始化会话。")
        draft = InitDraft.model_validate(session.draft or {})
        return self._finalize_init_session(context_key, draft)

    def _advance_init_session(
        self,
        *,
        context_key: str,
        latest_user_message: str,
    ) -> InputSubmissionResult:
        session = self.store.get_init_session(context_key)
        if session is None or session.status != "active":
            raise ValueError("当前没有进行中的初始化会话。")

        draft = InitDraft.model_validate(session.draft or {})
        turn = self.llm_provider.advance_init_session(latest_user_message, draft)
        if turn.ready_to_create and (turn.draft.title or "").strip():
            return self._finalize_init_session(
                context_key,
                turn.draft,
                assistant_message=turn.assistant_message,
            )

        self.store.upsert_init_session(
            context_key=context_key,
            draft=turn.draft.model_dump(),
            last_assistant_message=turn.assistant_message,
            status="active",
        )
        self.session.commit()
        return InputSubmissionResult(
            outcome="init_in_progress",
            message=turn.assistant_message,
        )

    def _finalize_init_session(
        self,
        context_key: str,
        draft: InitDraft,
        *,
        assistant_message: str | None = None,
    ) -> InputSubmissionResult:
        title = (draft.title or "").strip()
        if not title:
            raise ValueError("初始化草稿还缺少标题，请先补充标题后再完成。")

        aliases = [alias.strip() for alias in draft.aliases if alias.strip()]
        work_item = self.create_work_item(
            title=title,
            goal=(draft.goal or "").strip(),
            status=(draft.status or "active").strip() or "active",
            context_key=context_key,
            aliases=aliases,
        )
        self._seed_work_item_from_init_draft(work_item.id, draft)
        self.store.touch_work_item(work_item.id)
        self.store.enqueue_sync_job(work_item_id=work_item.id, reason="init_finalize")
        self.store.delete_init_session(context_key)
        self.session.commit()
        process_pending_jobs(self.session, settings=self.settings)

        message = f"已根据对话创建工作项：{work_item.title}"
        if assistant_message:
            message = f"{message}\n{assistant_message}"
        return InputSubmissionResult(
            outcome="accepted",
            message=message,
            work_item_id=work_item.id,
        )

    def _seed_work_item_from_init_draft(self, work_item_id: str, draft: InitDraft) -> None:
        background = (draft.background or "").strip()
        if background:
            self.store.create_event(
                work_item_id=work_item_id,
                event_type=EventType.NOTE,
                content=f"{INIT_BACKGROUND_PREFIX}{background}",
            )

        progress_summary = (draft.progress_summary or "").strip()
        if progress_summary:
            self.store.create_event(
                work_item_id=work_item_id,
                event_type=EventType.PROGRESS,
                content=progress_summary,
            )

        for todo_content in draft.todos:
            content = todo_content.strip()
            if not content:
                continue
            event = self.store.create_event(
                work_item_id=work_item_id,
                event_type=EventType.TODO_CREATED,
                content=content,
            )
            self.store.create_todo(
                work_item_id=work_item_id,
                content=content,
                status=TodoStatus.OPEN,
                source_channel=Channel.CLI,
                source_event_id=event.id,
            )

        for risk_content in draft.risks:
            content = risk_content.strip()
            if not content:
                continue
            self.store.create_event(
                work_item_id=work_item_id,
                event_type=EventType.RISK,
                content=content,
            )

        for note_content in draft.notes:
            content = note_content.strip()
            if not content:
                continue
            self.store.create_event(
                work_item_id=work_item_id,
                event_type=EventType.NOTE,
                content=content,
            )

    def _handle_command(
        self,
        command: ParsedCommand,
        context_key: str | None,
        input_entry_id: str | None,
        channel: Channel,
    ) -> InputSubmissionResult:
        if command.name == "init":
            return self.start_init_session(
                context_key=context_key or "cli:default",
                seed_title=command.args.get("title", "").strip() or None,
                seed_goal=command.args.get("goal", "").strip() or None,
                seed_status=command.args.get("status", "").strip() or None,
            )

        if command.name == "finish-init":
            return self.finish_init_session(context_key or "cli:default")

        if command.name == "cancel-init":
            return self.cancel_init_session(context_key or "cli:default")

        value = command.args.get("value", "").strip()
        if command.name == "use":
            work_item = self.use_work_item(value, context_key=context_key or "cli:default")
            return InputSubmissionResult(
                outcome="accepted",
                message=f"Switched active work item to {work_item.title}",
                work_item_id=work_item.id,
            )
        if command.name == "todo":
            init_session = self.store.get_init_session(context_key or "cli:default")
            if init_session is not None and init_session.status == "active":
                raise ValueError("当前正在进行初始化会话。请先完成它，或使用 /cancel-init 取消。")
            return self.add_explicit_todo(
                value,
                context_key=context_key or "cli:default",
                source_input_id=input_entry_id,
                channel=channel,
            )
        if command.name == "done":
            init_session = self.store.get_init_session(context_key or "cli:default")
            if init_session is not None and init_session.status == "active":
                raise ValueError("当前正在进行初始化会话。请先完成它，或使用 /cancel-init 取消。")
            return self.mark_todo_done(
                value,
                context_key=context_key or "cli:default",
                source_input_id=input_entry_id,
            )
        if command.name == "status":
            status = self.status(value, context_key=context_key)
            return InputSubmissionResult(
                outcome="accepted",
                message=f"{status.work_item.title} has {len(status.open_todos)} open todo(s)",
                work_item_id=status.work_item.id,
            )
        raise ValueError(f"unsupported command: {command.name}")

    def _persist_attachments(
        self, input_entry_id: str, uploaded_attachments: list[UploadedAttachment]
    ) -> list[str]:
        attachment_ids: list[str] = []
        target_dir = self.settings.attachments_dir / input_entry_id
        target_dir.mkdir(parents=True, exist_ok=True)
        for attachment in uploaded_attachments:
            filename = _safe_filename(attachment.filename)
            file_path = target_dir / filename
            file_path.write_bytes(attachment.content)
            saved = self.store.create_attachment(
                file_path=str(file_path.resolve()),
                file_type=attachment.content_type or "application/octet-stream",
                original_filename=attachment.filename,
                source_input_id=input_entry_id,
            )
            attachment_ids.append(saved.id)
        return attachment_ids

    def _materialize_events(
        self,
        *,
        work_item_id: str,
        source_input_id: str | None,
        channel: Channel,
        events: list[ExtractedEvent],
    ) -> None:
        for event in events:
            saved = self.store.create_event(
                work_item_id=work_item_id,
                event_type=event.type,
                content=event.content,
                source_input_id=source_input_id,
            )
            if event.type == EventType.TODO_CREATED:
                self.store.create_todo(
                    work_item_id=work_item_id,
                    content=event.content,
                    status=TodoStatus.OPEN,
                    source_channel=channel,
                    source_event_id=saved.id,
                )
            elif event.type == EventType.TODO_COMPLETED:
                todo = self.store.find_open_todo_match(work_item_id, event.content)
                if todo is not None:
                    self.store.mark_todo_done(todo)

    def _require_context_work_item(self, context_key: str):
        context = self.store.get_context(context_key)
        if context is None or not context.active_work_item_id:
            raise ValueError("No active work item in the current context. Use /use or /init first.")
        work_item = self.store.get_work_item(context.active_work_item_id)
        if work_item is None:
            raise ValueError("Active work item not found")
        return work_item

    @property
    def llm_provider(self) -> LlmProvider:
        if self._llm_provider is None:
            self._llm_provider = get_llm_provider(self.settings)
        return self._llm_provider
