from __future__ import annotations

from pathlib import Path

from markfold.domain.enums import Channel
from markfold.services import UploadedAttachment


def test_ingest_text_updates_todo_and_document(service) -> None:
    work_item = service.create_work_item(title="项目A", goal="完成 MVP")

    result = service.handle_input(
        raw_text="项目A 接口联调跑通了，还要补错误处理",
        channel=Channel.CLI,
        context_key="cli:default",
    )

    status = service.status(work_item.id)
    document = Path(status.work_item.markdown_doc_path).read_text(encoding="utf-8")

    assert result.outcome == "accepted"
    assert any("补错误处理" in todo.content for todo in status.open_todos)
    assert "接口联调跑通了" in document


def test_low_confidence_input_creates_review(service) -> None:
    service.create_work_item(title="项目A")
    service.create_work_item(title="项目B")

    result = service.handle_input(
        raw_text="今天开了个会",
        channel=Channel.CLI,
        context_key=None,
    )

    reviews = service.list_reviews()

    assert result.outcome == "pending_review"
    assert len(reviews) == 1
    assert reviews[0].status == "pending"


def test_import_work_item_appends_managed_block(service, tmp_path) -> None:
    source = tmp_path / "imported.md"
    source.write_text("# Imported\n\n- [ ] First todo\n", encoding="utf-8")

    work_item = service.import_work_item(str(source))
    updated = source.read_text(encoding="utf-8")
    status = service.status(work_item.id)

    assert "<!-- markfold:managed:start -->" in updated
    assert any(todo.content == "First todo" for todo in status.open_todos)


def test_attachment_only_input_is_persisted(service) -> None:
    work_item = service.create_work_item(title="图片项目")

    result = service.handle_input(
        raw_text="",
        channel=Channel.CLI,
        context_key="cli:default",
        explicit_work_item_id=work_item.id,
        uploaded_attachments=[
            UploadedAttachment(
                filename="demo.png",
                content_type="image/png",
                content=b"fake-image",
            )
        ],
    )

    document = Path(work_item.markdown_doc_path).read_text(encoding="utf-8")

    assert result.outcome == "accepted"
    assert "demo.png" in document


def test_init_session_progressively_builds_document(service) -> None:
    context_key = "cli:init"

    start = service.handle_input(
        raw_text="/init 项目A",
        channel=Channel.CLI,
        context_key=context_key,
    )
    assert start.outcome == "init_in_progress"

    step_goal = service.handle_input(
        raw_text="目标是先把 MVP 跑起来",
        channel=Channel.CLI,
        context_key=context_key,
    )
    assert step_goal.outcome == "init_in_progress"

    step_background = service.handle_input(
        raw_text="背景是这是一个用于归档 IDE 对话和任务进展的工具",
        channel=Channel.CLI,
        context_key=context_key,
    )
    assert step_background.outcome == "init_in_progress"

    finished = service.handle_input(
        raw_text="待办是补日志、补监控",
        channel=Channel.CLI,
        context_key=context_key,
    )

    assert finished.outcome == "accepted"
    assert finished.work_item_id is not None

    status = service.status(finished.work_item_id)
    document = Path(status.work_item.markdown_doc_path).read_text(encoding="utf-8")

    assert status.work_item.title == "项目A"
    assert status.work_item.goal == "先把 MVP 跑起来"
    assert any(todo.content == "补日志" for todo in status.open_todos)
    assert any(todo.content == "补监控" for todo in status.open_todos)
    assert "这是一个用于归档 IDE 对话和任务进展的工具" in document
