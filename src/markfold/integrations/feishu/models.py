from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FeishuMentionId(BaseModel):
    open_id: str | None = None
    user_id: str | None = None
    union_id: str | None = None


class FeishuNormalizedMessage(BaseModel):
    message_id: str
    chat_id: str
    chat_type: str | None = None
    sender_id: str | None = None
    sender_type: str | None = None
    message_type: str
    text: str = ""
    mentions: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def context_key(self) -> str:
        return f"feishu:{self.chat_id}"
