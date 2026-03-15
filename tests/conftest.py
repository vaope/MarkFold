from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import sessionmaker

from markfold.config import Settings
from markfold.domain.enums import EventType
from markfold.domain.schemas import ExtractedEvent, InitDraft, InitTurnResult, WorkItemChoice
from markfold.repositories.database import Base, build_engine
from markfold.repositories import models  # noqa: F401
from markfold.services import MarkFoldService


class FakeLlmProvider:
    def extract_events(self, raw_text: str) -> list[ExtractedEvent]:
        if "接口联调跑通了" in raw_text:
            return [
                ExtractedEvent(type=EventType.PROGRESS, content="接口联调跑通了"),
                ExtractedEvent(type=EventType.TODO_CREATED, content="补错误处理"),
            ]
        if "今天开了个会" in raw_text:
            return [ExtractedEvent(type=EventType.NOTE, content="今天开了个会")]
        if raw_text.strip():
            return [ExtractedEvent(type=EventType.NOTE, content=raw_text.strip())]
        return []

    def choose_work_item(self, raw_text, candidates):
        if "项目A" in raw_text:
            match = next((candidate for candidate in candidates if candidate.title == "项目A"), None)
            return WorkItemChoice(
                work_item_id=match.id if match else None,
                confidence=0.93 if match else 0.0,
                reason="fake llm matched 项目A",
            )
        return WorkItemChoice(work_item_id=None, confidence=0.2, reason="fake llm uncertain")

    def advance_init_session(self, latest_user_message: str, draft: InitDraft) -> InitTurnResult:
        updated = InitDraft.model_validate(draft.model_dump())
        text = latest_user_message.strip()

        if "当前已知标题是：" in text:
            title = text.split("当前已知标题是：", 1)[1].split("。", 1)[0].strip()
            if title:
                updated.title = title
        elif text.startswith("目标是"):
            updated.goal = text.removeprefix("目标是").strip()
        elif text.startswith("背景是"):
            updated.background = text.removeprefix("背景是").strip()
        elif text.startswith("待办是"):
            values = [
                item.strip()
                for item in text.removeprefix("待办是").replace("，", "、").split("、")
                if item.strip()
            ]
            updated.todos = values
        elif text.startswith("风险是"):
            values = [
                item.strip()
                for item in text.removeprefix("风险是").replace("，", "、").split("、")
                if item.strip()
            ]
            updated.risks = values
        elif text.startswith("备注是"):
            note = text.removeprefix("备注是").strip()
            if note:
                updated.notes = [*updated.notes, note]

        missing_fields: list[str] = []
        if not updated.title:
            missing_fields.append("title")
        if not updated.goal:
            missing_fields.append("goal")
        if not updated.background:
            missing_fields.append("background")

        if "title" in missing_fields:
            assistant_message = "先给这个工作项起个名字吧。"
        elif "goal" in missing_fields:
            assistant_message = "这个工作项当前最重要的目标是什么？"
        elif "background" in missing_fields:
            assistant_message = "补一句背景信息吧，我会把它写进首版文档。"
        elif not updated.todos:
            assistant_message = "如果你已经知道一些待办，可以继续告诉我；信息也已经足够创建了。"
        else:
            assistant_message = "信息已经比较完整了，我来创建首版工作项文档。"

        ready_to_create = not missing_fields and bool(updated.todos)
        return InitTurnResult(
            draft=updated,
            assistant_message=assistant_message,
            ready_to_create=ready_to_create,
            missing_fields=missing_fields,
        )


@pytest.fixture()
def service(tmp_path) -> Generator[MarkFoldService, None, None]:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        vault_root=tmp_path / "vault",
    )
    settings.ensure_directories()
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield MarkFoldService(session, settings=settings, llm_provider=FakeLlmProvider())
    finally:
        session.close()
