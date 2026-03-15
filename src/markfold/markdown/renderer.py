from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime


MANAGED_BLOCK_START = "<!-- markfold:managed:start -->"
MANAGED_BLOCK_END = "<!-- markfold:managed:end -->"
INIT_BACKGROUND_PREFIX = "[init_background] "


def _format_lines(values: list[str], prefix: str = "- ") -> str:
    if not values:
        return f"{prefix}暂无记录"
    return "\n".join(f"{prefix}{value}" for value in values)


def _format_todos(values: list[str], done: bool = False) -> str:
    if not values:
        marker = "[x]" if done else "[ ]"
        return f"- {marker} 暂无"
    marker = "[x]" if done else "[ ]"
    return "\n".join(f"- {marker} {value}" for value in values)


def _format_attachments(attachments: list[dict[str, str]]) -> str:
    if not attachments:
        return "- 暂无附件"
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for attachment in attachments:
        groups[attachment["date"]].append(attachment)
    chunks: list[str] = []
    for day in sorted(groups.keys()):
        chunks.append(f"### {day}")
        for item in groups[day]:
            chunks.append(f"- 说明：{item['label']}")
            chunks.append(f"- 图片：![]({item['relative_path']})")
    return "\n".join(chunks)


def render_managed_block(
    *,
    title: str,
    status: str,
    source_type: str,
    created_at: datetime,
    updated_at: datetime,
    goal: str,
    background: list[str],
    progress: list[str],
    open_todos: list[str],
    done_todos: list[str],
    risks: list[str],
    decisions: list[str],
    notes: list[str],
    attachments: list[dict[str, str]],
) -> str:
    goal_text = goal.strip() or "..."
    background_text = _format_lines(background, prefix="") if background else "..."
    lines = [
        MANAGED_BLOCK_START,
        "## 基本信息",
        f"- 状态：{status}",
        f"- 创建时间：{created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 最近更新时间：{updated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 来源：{source_type}",
        "",
        "## 背景",
        background_text,
        "",
        "## 当前目标",
        goal_text,
        "",
        "## 最新进展",
        _format_lines(progress),
        "",
        "## 当前 Todo",
        _format_todos(open_todos, done=False),
        "",
        "## 已完成事项",
        _format_todos(done_todos, done=True),
        "",
        "## 风险 / 阻塞",
        _format_lines(risks),
        "",
        "## 决策 / 备注",
        _format_lines([*decisions, *notes]),
        "",
        "## 附件记录",
        _format_attachments(attachments),
        MANAGED_BLOCK_END,
    ]
    return "\n".join(lines).strip() + "\n"


def render_full_document(title: str, managed_block: str) -> str:
    return f"# {title}\n\n{managed_block}".strip() + "\n"


def upsert_managed_block(original_content: str, managed_block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(MANAGED_BLOCK_START)}.*?{re.escape(MANAGED_BLOCK_END)}",
        re.DOTALL,
    )
    if pattern.search(original_content):
        updated = pattern.sub(managed_block.strip(), original_content)
    else:
        updated = original_content.rstrip() + "\n\n" + managed_block.strip() + "\n"
    return updated.rstrip() + "\n"
