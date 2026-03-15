from __future__ import annotations

from datetime import date, timedelta

from markfold.domain.enums import EventType
from markfold.domain.schemas import DailySummaryItem, ExtractedEvent, StatusResponse, TodoView, WorkItemView
from markfold.repositories.store import Store


def yesterday_date() -> date:
    return date.today() - timedelta(days=1)


def daily_summary(store: Store, target_date: date | None = None) -> list[DailySummaryItem]:
    target_date = target_date or yesterday_date()
    grouped: dict[str, DailySummaryItem] = {}
    for event in store.list_events_for_date(target_date):
        work_item = store.get_work_item(event.work_item_id)
        if work_item is None:
            continue
        current = grouped.setdefault(
            event.work_item_id,
            DailySummaryItem(work_item_id=work_item.id, title=work_item.title),
        )
        if event.type == EventType.PROGRESS:
            current.progress.append(event.content)
        elif event.type == EventType.TODO_COMPLETED:
            current.completed.append(event.content)
        elif event.type == EventType.RISK:
            current.risks.append(event.content)
        elif event.type == EventType.DECISION:
            current.decisions.append(event.content)
        elif event.type == EventType.NOTE:
            current.notes.append(event.content)
    return list(grouped.values())


def work_item_status(store: Store, title_or_id: str | None, context_key: str | None = None) -> StatusResponse:
    work_item = None
    if title_or_id:
        work_item = store.get_work_item(title_or_id) or store.find_work_item_by_title(title_or_id)
    elif context_key:
        context = store.get_context(context_key)
        if context and context.active_work_item_id:
            work_item = store.get_work_item(context.active_work_item_id)
    if work_item is None:
        raise ValueError("work item not found")

    recent_events = [
        ExtractedEvent(type=event.type, content=event.content)
        for event in store.list_recent_events(work_item.id, limit=10)
    ]
    open_todos = [TodoView.from_model(todo) for todo in store.list_open_todos(work_item.id)]
    return StatusResponse(
        work_item=WorkItemView.from_model(work_item),
        open_todos=open_todos,
        recent_events=recent_events,
    )
