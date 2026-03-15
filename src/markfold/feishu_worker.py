from __future__ import annotations

import asyncio
import logging

from markfold.config import get_settings
from markfold.integrations.feishu import (
    FeishuInboxCoordinator,
    FeishuMessageProcessor,
    FeishuWsGateway,
    get_feishu_client,
)
from markfold.repositories import SessionLocal, init_database


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    init_database()
    settings = get_settings()
    try:
        client = get_feishu_client()
    except ValueError as exc:
        logging.error(str(exc))
        raise SystemExit(1) from exc
    gateway = FeishuWsGateway(
        client=client,
        session_factory=SessionLocal,
        coordinator=FeishuInboxCoordinator(session_factory=SessionLocal),
        processor=FeishuMessageProcessor(
            session_factory=SessionLocal,
            client=client,
            settings=settings,
        ),
    )
    try:
        asyncio.run(gateway.run_forever())
    except KeyboardInterrupt:
        pass
