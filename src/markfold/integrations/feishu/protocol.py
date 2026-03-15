from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


class FrameType(IntEnum):
    CONTROL = 0
    DATA = 1


class MessageType(StrEnum):
    EVENT = "event"
    CARD = "card"
    PING = "ping"
    PONG = "pong"


class HeaderKey(StrEnum):
    TYPE = "type"
    MESSAGE_ID = "message_id"
    SUM = "sum"
    SEQ = "seq"
    TRACE_ID = "trace_id"
    BIZ_RT = "biz_rt"


_FRAME_CLASS = None


def _get_frame_class():
    global _FRAME_CLASS  # noqa: PLW0603
    if _FRAME_CLASS is not None:
        return _FRAME_CLASS

    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = "pbbp2.proto"
    file_proto.package = "pbbp2"
    file_proto.syntax = "proto3"

    header_message = file_proto.message_type.add()
    header_message.name = "Header"
    header_key = header_message.field.add()
    header_key.name = "key"
    header_key.number = 1
    header_key.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    header_key.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    header_value = header_message.field.add()
    header_value.name = "value"
    header_value.number = 2
    header_value.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    header_value.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

    frame_message = file_proto.message_type.add()
    frame_message.name = "Frame"
    fields = [
        ("SeqID", 1, descriptor_pb2.FieldDescriptorProto.TYPE_UINT64, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("LogID", 2, descriptor_pb2.FieldDescriptorProto.TYPE_UINT64, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("service", 3, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("method", 4, descriptor_pb2.FieldDescriptorProto.TYPE_INT32, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("headers", 5, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE, descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED),
        ("payloadEncoding", 6, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("payloadType", 7, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("payload", 8, descriptor_pb2.FieldDescriptorProto.TYPE_BYTES, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
        ("LogIDNew", 9, descriptor_pb2.FieldDescriptorProto.TYPE_STRING, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL),
    ]
    for name, number, field_type, label in fields:
        field = frame_message.field.add()
        field.name = name
        field.number = number
        field.label = label
        field.type = field_type
        if name == "headers":
            field.type_name = ".pbbp2.Header"

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)
    _FRAME_CLASS = message_factory.GetMessageClass(pool.FindMessageTypeByName("pbbp2.Frame"))
    return _FRAME_CLASS


@dataclass
class FeishuWsFrame:
    seq_id: int
    log_id: int
    service: int
    method: int
    headers: list[tuple[str, str]] = field(default_factory=list)
    payload_encoding: str | None = None
    payload_type: str | None = None
    payload: bytes = b""
    log_id_new: str | None = None

    def header_map(self) -> dict[str, str]:
        return {key: value for key, value in self.headers}


def encode_frame(frame: FeishuWsFrame) -> bytes:
    frame_class = _get_frame_class()
    message = frame_class()
    message.SeqID = frame.seq_id
    message.LogID = frame.log_id
    message.service = frame.service
    message.method = frame.method
    if frame.payload_encoding is not None:
        message.payloadEncoding = frame.payload_encoding
    if frame.payload_type is not None:
        message.payloadType = frame.payload_type
    if frame.payload:
        message.payload = frame.payload
    if frame.log_id_new is not None:
        message.LogIDNew = frame.log_id_new
    for key, value in frame.headers:
        header = message.headers.add()
        header.key = key
        header.value = value
    return message.SerializeToString()


def decode_frame(payload: bytes) -> FeishuWsFrame:
    frame_class = _get_frame_class()
    message = frame_class()
    message.ParseFromString(payload)
    return FeishuWsFrame(
        seq_id=int(message.SeqID),
        log_id=int(message.LogID),
        service=int(message.service),
        method=int(message.method),
        headers=[(header.key, header.value) for header in message.headers],
        payload_encoding=message.payloadEncoding or None,
        payload_type=message.payloadType or None,
        payload=bytes(message.payload or b""),
        log_id_new=message.LogIDNew or None,
    )


def build_ack_frame(source_frame: FeishuWsFrame, *, code: int, duration_ms: int) -> FeishuWsFrame:
    payload = json.dumps({"code": code}, ensure_ascii=False).encode("utf-8")
    headers = [*source_frame.headers, (HeaderKey.BIZ_RT, str(duration_ms))]
    return FeishuWsFrame(
        seq_id=source_frame.seq_id,
        log_id=source_frame.log_id,
        service=source_frame.service,
        method=source_frame.method,
        headers=headers,
        payload_encoding=source_frame.payload_encoding,
        payload_type=source_frame.payload_type,
        payload=payload,
        log_id_new=source_frame.log_id_new,
    )
