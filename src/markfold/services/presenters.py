from __future__ import annotations

from typing import TYPE_CHECKING

from markfold.domain.enums import EventType

if TYPE_CHECKING:
    from markfold.domain.schemas import InputSubmissionResult
    from markfold.services.markfold import MarkFoldService


EVENT_TYPE_LABELS = {
    EventType.PROGRESS: "进展",
    EventType.TODO_CREATED: "新增 Todo",
    EventType.TODO_COMPLETED: "完成 Todo",
    EventType.RISK: "风险",
    EventType.DECISION: "决策",
    EventType.NOTE: "备注",
}


def format_submission_result(
    service: MarkFoldService,
    result: InputSubmissionResult,
    context_key: str,
) -> str:
    lines = [result.message]
    if result.events:
        lines.append("我识别到了这些信息：")
        for event in result.events:
            label = EVENT_TYPE_LABELS.get(event.type, str(event.type))
            lines.append(f"- {label}：{event.content}")
    if result.review_id:
        lines.append(f"这条消息进入待确认队列，Review ID：{result.review_id}")
        lines.append("你可以去 Web 的待确认页面处理，或者补充更明确的工作项名称后再发一次。")
    if result.work_item_id:
        try:
            status = service.status(result.work_item_id, context_key=context_key)
        except ValueError:
            status = None
        if status is not None:
            lines.append(f"当前工作项：{status.work_item.title} [{status.work_item.status}]")
            if status.open_todos:
                lines.append("当前未完成 Todo：")
                for todo in status.open_todos[:5]:
                    lines.append(f"- {todo.content}")
    return "\n".join(lines)
