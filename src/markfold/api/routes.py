from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from markfold.domain.enums import Channel
from markfold.domain.schemas import (
    DoneCommandRequest,
    ImportWorkItemRequest,
    InitCommandRequest,
    InputSubmissionResult,
    ReviewResolveRequest,
    ReviewView,
    StatusResponse,
    TodoCommandRequest,
    TodoView,
    UseCommandRequest,
    WorkItemView,
)
from markfold.repositories import get_session
from markfold.services import MarkFoldService, UploadedAttachment


router = APIRouter(prefix="/api")


def get_service(session: Session = Depends(get_session)) -> MarkFoldService:
    return MarkFoldService(session)


@router.post("/inputs", response_model=InputSubmissionResult)
async def submit_input(
    raw_text: str = Form(""),
    channel: Channel = Form(Channel.CLI),
    context_key: str | None = Form("cli:default"),
    work_item_id: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
    service: MarkFoldService = Depends(get_service),
):
    attachments = [
        UploadedAttachment(
            filename=file.filename or "attachment.bin",
            content_type=file.content_type or "application/octet-stream",
            content=await file.read(),
        )
        for file in files or []
    ]
    try:
        return service.handle_input(
            raw_text=raw_text,
            channel=channel,
            context_key=context_key,
            uploaded_attachments=attachments,
            explicit_work_item_id=work_item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/work-items/import", response_model=WorkItemView)
def import_work_item(
    payload: ImportWorkItemRequest,
    service: MarkFoldService = Depends(get_service),
):
    try:
        return service.import_work_item(payload.path, context_key=payload.context_key)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/commands/init", response_model=InputSubmissionResult)
def init_command(payload: InitCommandRequest, service: MarkFoldService = Depends(get_service)):
    try:
        return service.start_init_session(
            context_key=payload.context_key or "cli:default",
            seed_title=(payload.title or "").strip() or None,
            seed_goal=payload.goal or None,
            seed_status=payload.status or "active",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/commands/use", response_model=WorkItemView)
def use_command(payload: UseCommandRequest, service: MarkFoldService = Depends(get_service)):
    try:
        return service.use_work_item(payload.title, context_key=payload.context_key or "cli:default")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/commands/todo", response_model=InputSubmissionResult)
def todo_command(payload: TodoCommandRequest, service: MarkFoldService = Depends(get_service)):
    try:
        return service.add_explicit_todo(payload.content, context_key=payload.context_key or "cli:default")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/commands/done", response_model=InputSubmissionResult)
def done_command(payload: DoneCommandRequest, service: MarkFoldService = Depends(get_service)):
    try:
        return service.mark_todo_done(payload.content, context_key=payload.context_key or "cli:default")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/work-items", response_model=list[WorkItemView])
def list_work_items(service: MarkFoldService = Depends(get_service)):
    return service.list_work_items()


@router.get("/work-items/{work_item_id}", response_model=StatusResponse)
def get_work_item(work_item_id: str, service: MarkFoldService = Depends(get_service)):
    try:
        return service.status(work_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/todos", response_model=list[TodoView])
def list_todos(work_item_id: str | None = None, service: MarkFoldService = Depends(get_service)):
    return service.list_open_todos(work_item_id)


@router.get("/queries/daily-summary")
def daily_summary(target_date: date | None = None, service: MarkFoldService = Depends(get_service)):
    return service.daily_summary(target_date)


@router.get("/queries/work-item-status", response_model=StatusResponse)
def work_item_status(
    title_or_id: str | None = None,
    context_key: str | None = "cli:default",
    service: MarkFoldService = Depends(get_service),
):
    try:
        return service.status(title_or_id, context_key=context_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reviews", response_model=list[ReviewView])
def list_reviews(service: MarkFoldService = Depends(get_service)):
    return service.list_reviews()


@router.post("/reviews/{review_id}/resolve", response_model=ReviewView)
def resolve_review(
    review_id: str,
    payload: ReviewResolveRequest,
    service: MarkFoldService = Depends(get_service),
):
    try:
        return service.resolve_review(review_id, payload.work_item_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
