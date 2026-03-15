from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from markfold.config import PROJECT_ROOT
from markfold.domain.enums import Channel
from markfold.repositories import get_session
from markfold.services import MarkFoldService, UploadedAttachment


router = APIRouter()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))


def get_service(session: Session = Depends(get_session)) -> MarkFoldService:
    return MarkFoldService(session)


@router.get("/")
def index(request: Request, service: MarkFoldService = Depends(get_service)):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "work_items": service.list_work_items(),
            "open_todos": service.list_open_todos(),
            "reviews": service.list_reviews(),
        },
    )


@router.get("/work-items/{work_item_id}")
def work_item_detail(
    work_item_id: str,
    request: Request,
    service: MarkFoldService = Depends(get_service),
):
    status = service.status(work_item_id)
    doc_path = Path(status.work_item.markdown_doc_path)
    markdown_content = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
    return templates.TemplateResponse(
        request=request,
        name="work_items/detail.html",
        context={
            "status": status,
            "markdown_content": markdown_content,
        },
    )


@router.post("/work-items/{work_item_id}/send")
async def send_to_work_item(
    work_item_id: str,
    raw_text: str = Form(""),
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
    service.handle_input(
        raw_text=raw_text,
        channel=Channel.WEB,
        context_key=f"web:{work_item_id}",
        uploaded_attachments=attachments,
        explicit_work_item_id=work_item_id,
    )
    return RedirectResponse(url=f"/work-items/{work_item_id}", status_code=303)


@router.get("/import")
def import_page(request: Request):
    return templates.TemplateResponse(request=request, name="import.html", context={})


@router.post("/import")
def import_work_item(
    path: str = Form(...),
    service: MarkFoldService = Depends(get_service),
):
    work_item = service.import_work_item(path, context_key="web:default")
    return RedirectResponse(url=f"/work-items/{work_item.id}", status_code=303)


@router.get("/reviews")
def reviews_page(request: Request, service: MarkFoldService = Depends(get_service)):
    return templates.TemplateResponse(
        request=request,
        name="reviews/list.html",
        context={
            "reviews": service.list_reviews(),
            "work_items": service.list_work_items(),
        },
    )


@router.post("/reviews/{review_id}/resolve")
def resolve_review(
    review_id: str,
    work_item_id: str = Form(...),
    notes: str = Form(""),
    service: MarkFoldService = Depends(get_service),
):
    service.resolve_review(review_id, work_item_id, notes=notes or None)
    return RedirectResponse(url="/reviews", status_code=303)


@router.get("/queries")
def queries_page(
    request: Request,
    target_date: date | None = None,
    service: MarkFoldService = Depends(get_service),
):
    return templates.TemplateResponse(
        request=request,
        name="queries/index.html",
        context={
            "summary": service.daily_summary(target_date),
            "open_todos": service.list_open_todos(),
            "target_date": target_date,
        },
    )
