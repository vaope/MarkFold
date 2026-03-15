from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker
from websockets.asyncio.server import serve

from markfold.domain.enums import FeishuInboundStatus
from markfold.integrations.feishu import (
    DownloadedResource,
    FeishuInboxCoordinator,
    FeishuMessageProcessor,
    FeishuWsConnectConfig,
    FeishuWsGateway,
)
from markfold.integrations.feishu.protocol import (
    FeishuWsFrame,
    FrameType,
    HeaderKey,
    MessageType,
    decode_frame,
    encode_frame,
)
from markfold.repositories.store import Store


class FakeFeishuClient:
    def __init__(self, connect_config: FeishuWsConnectConfig | None = None) -> None:
        self.connect_config = connect_config
        self.sent_messages: list[dict] = []

    def send_text_message(self, receive_id: str, text: str, *, receive_id_type: str = "chat_id") -> dict:
        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "text": text,
        }
        self.sent_messages.append(payload)
        return {"data": payload}

    def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
        fallback_filename: str | None = None,
    ) -> DownloadedResource:
        return DownloadedResource(
            filename=fallback_filename or "demo.png",
            content_type="image/png",
            content=b"fake-image",
        )

    def get_ws_connect_config(self) -> FeishuWsConnectConfig:
        if self.connect_config is None:
            raise AssertionError("connect_config was not configured for this test")
        return self.connect_config


def _session_factory(service):
    return sessionmaker(
        bind=service.session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def _build_text_event_payload(
    *,
    message_id: str,
    chat_id: str,
    text: str,
    chat_type: str = "p2p",
    mentions: list[dict] | None = None,
) -> dict:
    event: dict = {
        "sender": {
            "sender_id": {"open_id": "ou_user_1"},
            "sender_type": "user",
        },
        "message": {
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "message_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
    }
    if mentions is not None:
        event["mentions"] = mentions
    return {
        "header": {"event_type": "im.message.receive_v1"},
        "event": event,
    }


def _build_image_event_payload(
    *,
    message_id: str,
    chat_id: str,
    chat_type: str = "p2p",
) -> dict:
    return {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_user_1"},
                "sender_type": "user",
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "image",
                "content": json.dumps({"image_key": "img_123"}, ensure_ascii=False),
            },
        },
    }


def test_protocol_frame_round_trip() -> None:
    frame = FeishuWsFrame(
        seq_id=1,
        log_id=2,
        service=3,
        method=FrameType.DATA,
        headers=[
            (HeaderKey.TYPE, MessageType.EVENT),
            (HeaderKey.MESSAGE_ID, "msg-1"),
        ],
        payload=b'{"hello":"world"}',
        payload_type="application/json",
    )

    decoded = decode_frame(encode_frame(frame))

    assert decoded.seq_id == 1
    assert decoded.log_id == 2
    assert decoded.service == 3
    assert decoded.method == FrameType.DATA
    assert decoded.header_map()[HeaderKey.MESSAGE_ID] == "msg-1"
    assert decoded.payload == b'{"hello":"world"}'


def test_coordinator_and_processor_archive_private_text(service) -> None:
    session_factory = _session_factory(service)
    client = FakeFeishuClient()
    coordinator = FeishuInboxCoordinator(session_factory=session_factory)
    processor = FeishuMessageProcessor(
        session_factory=session_factory,
        client=client,
        settings=service.settings,
        llm_provider=service._llm_provider,
    )

    decision = coordinator.record_event_payload(
        _build_text_event_payload(message_id="om_text_1", chat_id="oc_chat_1", text="/init 项目A")
    )

    assert decision.status == FeishuInboundStatus.PENDING
    assert decision.should_queue is True

    processor.process_message_id("om_text_1")

    with session_factory() as session:
        store = Store(session)
        inbound = store.get_feishu_inbound_message("om_text_1")

    assert inbound is not None
    assert inbound.status == FeishuInboundStatus.DONE
    assert client.sent_messages
    assert "目标" in client.sent_messages[0]["text"]


def test_group_message_without_mention_is_ignored(service) -> None:
    session_factory = _session_factory(service)
    coordinator = FeishuInboxCoordinator(session_factory=session_factory)

    decision = coordinator.record_event_payload(
        _build_text_event_payload(
            message_id="om_group_1",
            chat_id="oc_group_1",
            text="今天讨论一下排期",
            chat_type="group",
        )
    )

    with session_factory() as session:
        store = Store(session)
        inbound = store.get_feishu_inbound_message("om_group_1")

    assert decision.status == FeishuInboundStatus.IGNORED
    assert decision.should_queue is False
    assert inbound is not None
    assert inbound.status == FeishuInboundStatus.IGNORED


def test_processor_archives_image_to_active_context(service) -> None:
    session_factory = _session_factory(service)
    work_item = service.create_work_item(title="图片项目", context_key="feishu:oc_chat_img")
    client = FakeFeishuClient()
    coordinator = FeishuInboxCoordinator(session_factory=session_factory)
    processor = FeishuMessageProcessor(
        session_factory=session_factory,
        client=client,
        settings=service.settings,
        llm_provider=service._llm_provider,
    )

    decision = coordinator.record_event_payload(
        _build_image_event_payload(message_id="om_img_1", chat_id="oc_chat_img")
    )
    processor.process_message_id("om_img_1")
    document = Path(work_item.markdown_doc_path).read_text(encoding="utf-8")

    assert decision.status == FeishuInboundStatus.PENDING
    assert "demo.png" in document
    assert "当前工作项：图片项目" in client.sent_messages[0]["text"]


@pytest.mark.anyio
async def test_ws_gateway_acknowledges_and_processes_text_message(service, free_tcp_port: int) -> None:
    ack_payloads: list[dict] = []
    event_payload = _build_text_event_payload(
        message_id="om_ws_1",
        chat_id="oc_chat_ws",
        text="/init 项目A",
    )
    event_frame = FeishuWsFrame(
        seq_id=1,
        log_id=2,
        service=99,
        method=FrameType.DATA,
        headers=[
            (HeaderKey.TYPE, MessageType.EVENT),
            (HeaderKey.MESSAGE_ID, "om_ws_1"),
            (HeaderKey.SUM, "1"),
            (HeaderKey.SEQ, "1"),
            (HeaderKey.TRACE_ID, "trace-1"),
        ],
        payload=json.dumps(event_payload, ensure_ascii=False).encode("utf-8"),
    )

    async def ws_handler(websocket) -> None:
        await websocket.send(encode_frame(event_frame))
        raw_ack = await websocket.recv()
        ack_frame = decode_frame(bytes(raw_ack))
        ack_payloads.append(json.loads(ack_frame.payload.decode("utf-8")))
        await websocket.close()

    session_factory = _session_factory(service)
    connect_config = FeishuWsConnectConfig(
        url=f"ws://127.0.0.1:{free_tcp_port}/ws?device_id=device_1&service_id=99",
        service_id=99,
        device_id="device_1",
        ping_interval_ms=60_000,
        reconnect_count=0,
        reconnect_interval_ms=1_000,
        reconnect_nonce_ms=0,
    )
    client = FakeFeishuClient(connect_config=connect_config)
    gateway = FeishuWsGateway(
        client=client,
        session_factory=session_factory,
        coordinator=FeishuInboxCoordinator(session_factory=session_factory),
        processor=FeishuMessageProcessor(
            session_factory=session_factory,
            client=client,
            settings=service.settings,
            llm_provider=service._llm_provider,
        ),
    )

    async with serve(ws_handler, "127.0.0.1", free_tcp_port):
        await gateway.run_once(connect_config)

    with session_factory() as session:
        store = Store(session)
        inbound = store.get_feishu_inbound_message("om_ws_1")

    assert ack_payloads == [{"code": 200}]
    assert inbound is not None
    assert inbound.status == FeishuInboundStatus.DONE
    assert client.sent_messages
    assert "目标" in client.sent_messages[0]["text"]
