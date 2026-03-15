from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from markfold.config import Settings, get_settings
from markfold.domain.enums import EventType, SyncJobStatus
from markfold.markdown.renderer import (
    INIT_BACKGROUND_PREFIX,
    render_full_document,
    render_managed_block,
    upsert_managed_block,
)
from markfold.repositories.models import DocumentSyncJob
from markfold.repositories.store import Store


def _relative_attachment_path(doc_path: Path, attachment_path: Path) -> str:
    try:
        return os.path.relpath(attachment_path, start=doc_path.parent).replace("\\", "/")
    except ValueError:
        return attachment_path.as_posix()


def _build_document_content(session: Session, work_item_id: str) -> tuple[Path, str]:
    store = Store(session)
    work_item = store.get_work_item(work_item_id)
    if work_item is None:
        raise ValueError(f"work item {work_item_id} not found")

    doc_path = Path(work_item.markdown_doc_path)
    if not doc_path.is_absolute():
        doc_path = Path.cwd() / doc_path
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    progress: list[str] = []
    background: list[str] = []
    risks: list[str] = []
    decisions: list[str] = []
    notes: list[str] = []
    for event in store.list_events_for_work_item(work_item_id):
        if event.type == EventType.PROGRESS:
            line = f"{event.happened_at.strftime('%Y-%m-%d')}：{event.content}"
            progress.append(line)
        elif event.type == EventType.RISK:
            line = f"{event.happened_at.strftime('%Y-%m-%d')}：{event.content}"
            risks.append(line)
        elif event.type == EventType.DECISION:
            line = f"{event.happened_at.strftime('%Y-%m-%d')}：{event.content}"
            decisions.append(line)
        elif event.type == EventType.NOTE:
            if event.content.startswith(INIT_BACKGROUND_PREFIX):
                background.append(event.content.removeprefix(INIT_BACKGROUND_PREFIX).strip())
            else:
                line = f"{event.happened_at.strftime('%Y-%m-%d')}：{event.content}"
                notes.append(line)

    attachments = []
    for attachment in store.list_attachments_for_work_item(work_item_id):
        absolute_attachment = Path(attachment.file_path)
        if not absolute_attachment.is_absolute():
            absolute_attachment = Path.cwd() / absolute_attachment
        attachments.append(
            {
                "date": attachment.created_at.strftime("%Y-%m-%d"),
                "label": attachment.original_filename,
                "relative_path": _relative_attachment_path(doc_path, absolute_attachment),
            }
        )

    managed_block = render_managed_block(
        title=work_item.title,
        status=work_item.status,
        source_type=work_item.source_type,
        created_at=work_item.created_at,
        updated_at=work_item.updated_at,
        goal=work_item.goal,
        background=background,
        progress=progress,
        open_todos=[todo.content for todo in store.list_open_todos(work_item_id)],
        done_todos=[todo.content for todo in store.list_done_todos(work_item_id)],
        risks=risks,
        decisions=decisions,
        notes=notes,
        attachments=attachments,
    )

    if doc_path.exists():
        original_content = doc_path.read_text(encoding="utf-8")
        updated_content = upsert_managed_block(original_content, managed_block)
    else:
        updated_content = render_full_document(work_item.title, managed_block)

    return doc_path, updated_content


def sync_work_item_now(session: Session, work_item_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    settings.ensure_directories()
    doc_path, updated_content = _build_document_content(session, work_item_id)
    doc_path.write_text(updated_content, encoding="utf-8")


def process_job(session: Session, job: DocumentSyncJob, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    store = Store(session)
    job.status = SyncJobStatus.PROCESSING
    job.attempts += 1
    session.add(job)
    session.flush()
    try:
        sync_work_item_now(session, job.work_item_id, settings=settings)
        job.status = SyncJobStatus.DONE
        job.error_message = None
        session.add(job)
        session.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        tracked_job = store.get_sync_job(job.id)
        if tracked_job is not None:
            tracked_job.status = SyncJobStatus.FAILED
            tracked_job.error_message = str(exc)
            session.add(tracked_job)
            session.commit()
        return False


def process_pending_jobs(session: Session, settings: Settings | None = None, limit: int = 20) -> int:
    settings = settings or get_settings()
    processed = 0
    store = Store(session)
    jobs = store.list_pending_sync_jobs(limit=limit)
    for job in jobs:
        if process_job(session, job, settings=settings):
            processed += 1
    return processed
