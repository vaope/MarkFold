from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker

from markfold.config import Settings, get_settings
from markfold.domain.enums import Channel, FeishuInboundStatus
from markfold.integrations.feishu.client import DownloadedResource, FeishuApiError, FeishuClient
from markfold.integrations.feishu.models import FeishuNormalizedMessage
from markfold.integrations.llm.base import LlmProvider
from markfold.repositories.store import Store
from markfold.services import MarkFoldService, UploadedAttachment
from markfold.services.presenters import format_submission_result


logger = logging.getLogger(__name__)

MENTION_TAG_RE = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)
RESOURCE_KEYS = {
    "image": "image_key",
    "file": "file_key",
}


@dataclass
class FeishuInboxDecision:
    message_id: str | None = None
    status: str = FeishuInboundStatus.PENDING
    should_queue: bool = False


def normalize_event_payload(payload: dict[str, Any]) -> FeishuNormalizedMessage | None:
    header = payload.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None

    event = payload.get("event") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    message = event.get("message") or {}
    message_id = message.get("message_id")
    chat_id = message.get("chat_id")
    message_type = message.get("message_type")
    if not message_id or not chat_id or not message_type:
        raise ValueError("Feishu event payload missing message_id, chat_id, or message_type.")

    parsed_content = _parse_content(message.get("content"))
    raw_text = parsed_content.get("text", "") if isinstance(parsed_content, dict) else ""
    mentions = _extract_mentions(event.get("mentions") or message.get("mentions") or [])
    if "<at" in raw_text and not mentions:
        mentions = ["markup_mention"]

    return FeishuNormalizedMessage(
        message_id=message_id,
        chat_id=chat_id,
        chat_type=message.get("chat_type"),
        sender_id=sender_id.get("open_id") or sender_id.get("user_id") or sender_id.get("union_id"),
        sender_type=sender.get("sender_type"),
        message_type=message_type,
        text=MENTION_TAG_RE.sub("", raw_text).strip(),
        mentions=mentions,
        payload={
            "content": parsed_content if isinstance(parsed_content, dict) else {},
            "raw_message": message,
            "raw_sender": sender,
        },
    )


def infer_initial_status(message: FeishuNormalizedMessage) -> tuple[str, str | None]:
    if message.sender_type and message.sender_type != "user":
        return FeishuInboundStatus.IGNORED, "ignore non-user sender"
    if (message.chat_type or "").lower() != "p2p" and not message.mentions:
        return FeishuInboundStatus.IGNORED, "ignore group message without bot mention"
    return FeishuInboundStatus.PENDING, None


class FeishuInboxCoordinator:
    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        max_attempts: int = 3,
    ):
        self.session_factory = session_factory
        self.max_attempts = max_attempts

    def record_event_payload(self, payload: dict[str, Any]) -> FeishuInboxDecision:
        message = normalize_event_payload(payload)
        if message is None:
            return FeishuInboxDecision(status=FeishuInboundStatus.IGNORED, should_queue=False)

        initial_status, last_error = infer_initial_status(message)
        with self.session_factory() as session:
            store = Store(session)
            existing = store.get_feishu_inbound_message(message.message_id)
            if existing is not None:
                if existing.status in {
                    FeishuInboundStatus.DONE,
                    FeishuInboundStatus.PROCESSING,
                    FeishuInboundStatus.IGNORED,
                }:
                    return FeishuInboxDecision(message_id=existing.message_id, status=existing.status)
                if existing.status == FeishuInboundStatus.PENDING:
                    return FeishuInboxDecision(
                        message_id=existing.message_id,
                        status=existing.status,
                        should_queue=True,
                    )
                if (
                    existing.status == FeishuInboundStatus.FAILED
                    and existing.attempts < self.max_attempts
                ):
                    return FeishuInboxDecision(
                        message_id=existing.message_id,
                        status=existing.status,
                        should_queue=True,
                    )
                return FeishuInboxDecision(message_id=existing.message_id, status=existing.status)

            store.create_feishu_inbound_message(
                message_id=message.message_id,
                chat_id=message.chat_id,
                chat_type=message.chat_type,
                sender_id=message.sender_id,
                sender_type=message.sender_type,
                message_type=message.message_type,
                mentions=message.mentions,
                payload=message.model_dump(),
                status=initial_status,
                last_error=last_error,
            )
            session.commit()
            return FeishuInboxDecision(
                message_id=message.message_id,
                status=initial_status,
                should_queue=initial_status == FeishuInboundStatus.PENDING,
            )

    def list_recoverable_message_ids(self, limit: int = 100) -> list[str]:
        with self.session_factory() as session:
            store = Store(session)
            messages = store.list_feishu_inbound_messages_by_status(
                [
                    FeishuInboundStatus.PENDING,
                    FeishuInboundStatus.PROCESSING,
                    FeishuInboundStatus.FAILED,
                ],
                max_attempts=self.max_attempts,
                limit=limit,
            )
            return [message.message_id for message in messages]


class FeishuMessageProcessor:
    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        client: FeishuClient,
        settings: Settings | None = None,
        llm_provider: LlmProvider | None = None,
    ):
        self.session_factory = session_factory
        self.client = client
        self.settings = settings or get_settings()
        self.llm_provider = llm_provider

    def process_message_id(self, message_id: str) -> None:
        normalized = self._mark_processing(message_id)
        if normalized is None:
            return

        try:
            reply_text = self._process_normalized_message(normalized)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to process Feishu inbound message %s", message_id)
            self._mark_failed(message_id, str(exc))
            self._safe_reply(normalized.chat_id, f"处理这条飞书消息时出错了：{exc}")
            return

        self._mark_done(message_id)
        if reply_text:
            self._safe_reply(normalized.chat_id, reply_text)

    def _mark_processing(self, message_id: str) -> FeishuNormalizedMessage | None:
        with self.session_factory() as session:
            store = Store(session)
            inbound = store.get_feishu_inbound_message(message_id)
            if inbound is None:
                return None
            if inbound.status in {FeishuInboundStatus.DONE, FeishuInboundStatus.IGNORED}:
                return None
            store.update_feishu_inbound_message(
                inbound,
                status=FeishuInboundStatus.PROCESSING,
                attempts=inbound.attempts + 1,
                last_error=None,
            )
            session.commit()
            return FeishuNormalizedMessage.model_validate(inbound.payload or {})

    def _mark_done(self, message_id: str) -> None:
        with self.session_factory() as session:
            store = Store(session)
            inbound = store.get_feishu_inbound_message(message_id)
            if inbound is None:
                return
            store.update_feishu_inbound_message(
                inbound,
                status=FeishuInboundStatus.DONE,
                processed_at=self._utcnow(),
                last_error=None,
            )
            session.commit()

    def _mark_failed(self, message_id: str, error_message: str) -> None:
        with self.session_factory() as session:
            store = Store(session)
            inbound = store.get_feishu_inbound_message(message_id)
            if inbound is None:
                return
            store.update_feishu_inbound_message(
                inbound,
                status=FeishuInboundStatus.FAILED,
                processed_at=self._utcnow(),
                last_error=error_message,
            )
            session.commit()

    def _process_normalized_message(self, message: FeishuNormalizedMessage) -> str:
        raw_text, attachments = self._extract_input(message)
        with self.session_factory() as session:
            service = MarkFoldService(
                session,
                settings=self.settings,
                llm_provider=self.llm_provider,
            )
            result = service.handle_input(
                raw_text=raw_text,
                channel=Channel.FEISHU_MOBILE,
                context_key=message.context_key,
                uploaded_attachments=attachments,
            )
            return format_submission_result(service, result, message.context_key)

    def _extract_input(self, message: FeishuNormalizedMessage) -> tuple[str, list[UploadedAttachment]]:
        if message.message_type == "text":
            if not message.text.strip():
                raise ValueError("请在消息里输入要记录的内容。")
            return message.text.strip(), []

        if message.message_type in RESOURCE_KEYS:
            content = message.payload.get("content", {})
            resource_key = content.get(RESOURCE_KEYS[message.message_type])
            if not resource_key:
                raise ValueError(f"飞书消息里缺少 {RESOURCE_KEYS[message.message_type]}。")
            resource = self.client.download_message_resource(
                message_id=message.message_id,
                file_key=resource_key,
                resource_type=message.message_type,
                fallback_filename=content.get("file_name"),
            )
            return "", [self._to_uploaded_attachment(resource)]

        raise ValueError(
            f"暂不支持飞书消息类型：{message.message_type}。当前支持 text、image、file。"
        )

    def _safe_reply(self, chat_id: str, text: str) -> None:
        try:
            self.client.send_text_message(chat_id, text)
        except FeishuApiError:
            logger.exception("Failed to send Feishu reply to chat %s", chat_id)

    @staticmethod
    def _to_uploaded_attachment(resource: DownloadedResource) -> UploadedAttachment:
        return UploadedAttachment(
            filename=resource.filename,
            content_type=resource.content_type,
            content=resource.content,
        )

    @staticmethod
    def _utcnow():
        from markfold.repositories.models import utcnow

        return utcnow()


def _parse_content(raw_content: Any) -> dict[str, Any]:
    if isinstance(raw_content, dict):
        return raw_content
    if not raw_content:
        return {}
    if isinstance(raw_content, str):
        return json.loads(raw_content)
    raise ValueError("Feishu message content is not valid JSON.")


def _extract_mentions(raw_mentions: list[Any]) -> list[str]:
    mentions: list[str] = []
    for raw_mention in raw_mentions:
        if not isinstance(raw_mention, dict):
            continue
        mention_id = raw_mention.get("id") or {}
        if isinstance(mention_id, dict):
            mention_value = (
                mention_id.get("open_id")
                or mention_id.get("user_id")
                or mention_id.get("union_id")
            )
            if mention_value:
                mentions.append(str(mention_value))
                continue
        key = raw_mention.get("key")
        if key:
            mentions.append(str(key))
    return mentions
