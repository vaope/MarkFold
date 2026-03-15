from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker
from websockets.asyncio.client import ClientConnection, connect

from markfold.integrations.feishu.client import FeishuClient, FeishuWsConnectConfig
from markfold.integrations.feishu.handler import FeishuInboxCoordinator, FeishuMessageProcessor
from markfold.integrations.feishu.protocol import (
    FrameType,
    HeaderKey,
    MessageType,
    build_ack_frame,
    decode_frame,
    encode_frame,
)


logger = logging.getLogger(__name__)


@dataclass
class _MergedEventParts:
    total_parts: int
    parts: dict[int, bytes]
    created_at: float


class _FrameChunkBuffer:
    def __init__(self, *, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._buffers: dict[str, _MergedEventParts] = {}

    def add(self, headers: dict[str, str], payload: bytes) -> bytes | None:
        self._prune()
        message_id = headers.get(HeaderKey.MESSAGE_ID)
        total_parts = int(headers.get(HeaderKey.SUM, "1") or 1)
        seq = int(headers.get(HeaderKey.SEQ, "1") or 1)
        if not message_id or total_parts <= 1:
            return payload

        buffer = self._buffers.setdefault(
            message_id,
            _MergedEventParts(total_parts=total_parts, parts={}, created_at=time.monotonic()),
        )
        buffer.parts[seq] = payload
        if len(buffer.parts) < buffer.total_parts:
            return None

        merged = b"".join(buffer.parts[index] for index in sorted(buffer.parts))
        self._buffers.pop(message_id, None)
        return merged

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [
            message_id
            for message_id, buffer in self._buffers.items()
            if now - buffer.created_at > self.ttl_seconds
        ]
        for message_id in expired:
            self._buffers.pop(message_id, None)


class FeishuWsGateway:
    def __init__(
        self,
        *,
        client: FeishuClient,
        session_factory: sessionmaker,
        coordinator: FeishuInboxCoordinator,
        processor: FeishuMessageProcessor,
        queue_size: int = 200,
    ):
        self.client = client
        self.session_factory = session_factory
        self.coordinator = coordinator
        self.processor = processor
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
        self.chunk_buffer = _FrameChunkBuffer()
        self._scheduled_ids: set[str] = set()
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        consumer_task = asyncio.create_task(self._consume_queue())
        try:
            await self._recover_pending_messages()
            while not self._stop_event.is_set():
                try:
                    connect_config = await asyncio.to_thread(self.client.get_ws_connect_config)
                    await self._run_single_connection(connect_config)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Feishu WS gateway connection failed: %s", exc)
                    await asyncio.sleep(3)
        finally:
            consumer_task.cancel()
            await asyncio.gather(consumer_task, return_exceptions=True)

    async def run_once(self, connect_config: FeishuWsConnectConfig | None = None) -> None:
        consumer_task = asyncio.create_task(self._consume_queue())
        try:
            await self._recover_pending_messages()
            resolved_config = connect_config or await asyncio.to_thread(self.client.get_ws_connect_config)
            await self._run_single_connection(resolved_config)
            await self.queue.join()
        finally:
            consumer_task.cancel()
            await asyncio.gather(consumer_task, return_exceptions=True)

    def stop(self) -> None:
        self._stop_event.set()

    async def _run_single_connection(self, connect_config: FeishuWsConnectConfig) -> None:
        current_config = connect_config
        logger.info("Connecting Feishu WS: %s", current_config.url)
        async with connect(
            current_config.url,
            ping_interval=None,
            ping_timeout=None,
            max_size=None,
        ) as websocket:
            ping_task = asyncio.create_task(self._ping_loop(websocket, lambda: current_config))
            try:
                async for raw_message in websocket:
                    if isinstance(raw_message, str):
                        frame_bytes = raw_message.encode("utf-8")
                    else:
                        frame_bytes = bytes(raw_message)
                    maybe_new_config = await self._handle_frame(websocket, frame_bytes, current_config)
                    if maybe_new_config is not None:
                        current_config = maybe_new_config
                    if self._stop_event.is_set():
                        break
            finally:
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)

        if self._stop_event.is_set():
            return

        sleep_ms = current_config.reconnect_interval_ms + int(
            current_config.reconnect_nonce_ms * random.random()
        )
        logger.info("Feishu WS disconnected, reconnecting in %.2fs", sleep_ms / 1000)
        await asyncio.sleep(sleep_ms / 1000)

    async def _handle_frame(
        self,
        websocket: ClientConnection,
        frame_bytes: bytes,
        connect_config: FeishuWsConnectConfig,
    ) -> FeishuWsConnectConfig | None:
        frame = decode_frame(frame_bytes)
        headers = frame.header_map()
        message_type = headers.get(HeaderKey.TYPE)

        if frame.method == FrameType.CONTROL:
            if message_type == MessageType.PONG and frame.payload:
                return _update_connect_config(connect_config, frame.payload)
            return None

        if frame.method != FrameType.DATA or message_type != MessageType.EVENT:
            return None

        start = time.perf_counter()
        ack_code = 200
        try:
            merged_payload = self.chunk_buffer.add(headers, frame.payload)
            if merged_payload is None:
                return None
            event_payload = json.loads(merged_payload.decode("utf-8"))
            decision = await asyncio.to_thread(self.coordinator.record_event_payload, event_payload)
            if decision.should_queue and decision.message_id:
                queued = self._schedule_message(decision.message_id)
                if not queued:
                    ack_code = 500
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to accept Feishu event frame: %s", exc)
            ack_code = 500
        finally:
            if frame.method == FrameType.DATA and message_type == MessageType.EVENT:
                merged_payload = locals().get("merged_payload")
                if merged_payload is not None:
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    ack_frame = build_ack_frame(frame, code=ack_code, duration_ms=duration_ms)
                    await websocket.send(encode_frame(ack_frame))
        return None

    async def _ping_loop(
        self,
        websocket: ClientConnection,
        get_connect_config,
    ) -> None:
        while True:
            current_config = get_connect_config()
            await asyncio.sleep(current_config.ping_interval_ms / 1000)
            if websocket.state.name != "OPEN":
                return
            ping_frame = encode_frame(
                build_ping_frame(service_id=current_config.service_id)
            )
            await websocket.send(ping_frame)

    async def _consume_queue(self) -> None:
        while True:
            message_id = await self.queue.get()
            self._scheduled_ids.discard(message_id)
            try:
                await asyncio.to_thread(self.processor.process_message_id, message_id)
            finally:
                self.queue.task_done()

    async def _recover_pending_messages(self) -> None:
        message_ids = await asyncio.to_thread(self.coordinator.list_recoverable_message_ids)
        for message_id in message_ids:
            self._schedule_message(message_id)

    def _schedule_message(self, message_id: str) -> bool:
        if message_id in self._scheduled_ids:
            return True
        try:
            self.queue.put_nowait(message_id)
        except asyncio.QueueFull:
            logger.warning("Feishu inbound queue is full, message %s will wait for retry", message_id)
            return False
        self._scheduled_ids.add(message_id)
        return True


def build_ping_frame(*, service_id: int):
    from markfold.integrations.feishu.protocol import FeishuWsFrame

    return FeishuWsFrame(
        seq_id=0,
        log_id=0,
        service=service_id,
        method=FrameType.CONTROL,
        headers=[(HeaderKey.TYPE, MessageType.PING)],
        payload=b"",
    )


def _update_connect_config(
    connect_config: FeishuWsConnectConfig,
    payload: bytes,
) -> FeishuWsConnectConfig:
    data = json.loads(payload.decode("utf-8"))
    return FeishuWsConnectConfig(
        url=connect_config.url,
        service_id=connect_config.service_id,
        device_id=connect_config.device_id,
        ping_interval_ms=int(data.get("PingInterval", connect_config.ping_interval_ms // 1000)) * 1000,
        reconnect_count=int(data.get("ReconnectCount", connect_config.reconnect_count)),
        reconnect_interval_ms=int(
            data.get("ReconnectInterval", connect_config.reconnect_interval_ms // 1000)
        )
        * 1000,
        reconnect_nonce_ms=int(
            data.get("ReconnectNonce", connect_config.reconnect_nonce_ms // 1000)
        )
        * 1000,
    )
