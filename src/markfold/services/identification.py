from __future__ import annotations

from markfold.domain.schemas import WorkItemCandidate, WorkItemChoice
from markfold.integrations.llm.base import LlmProvider
from markfold.repositories.store import Store


def identify_work_item(
    *,
    store: Store,
    raw_text: str,
    context_key: str | None,
    llm_provider: LlmProvider,
) -> tuple[WorkItemChoice, list[str]]:
    work_items = store.list_work_items()
    if not work_items:
        return WorkItemChoice(work_item_id=None, confidence=0.0, reason="no work items"), []

    if context_key:
        context = store.get_context(context_key)
        if context is not None and context.active_work_item_id:
            return (
                WorkItemChoice(
                    work_item_id=context.active_work_item_id,
                    confidence=1.0,
                    reason="active context",
                ),
                [context.active_work_item_id],
            )

    candidates: list[WorkItemCandidate] = []
    for item in work_items:
        candidates.append(
            WorkItemCandidate(
                id=item.id,
                title=item.title,
                aliases=item.aliases or [],
                open_todos=[todo.content for todo in store.list_open_todos(item.id)],
            )
        )

    if not candidates:
        return WorkItemChoice(work_item_id=None, confidence=0.0, reason="no candidates"), []

    llm_choice = llm_provider.choose_work_item(raw_text, candidates)
    return llm_choice, [candidate.id for candidate in candidates]
