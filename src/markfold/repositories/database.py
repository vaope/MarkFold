from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from markfold.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings):
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


@lru_cache
def get_engine():
    return build_engine(get_settings())


SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def init_database() -> None:
    from markfold.repositories import models  # noqa: F401

    settings = get_settings()
    settings.ensure_directories()
    Base.metadata.create_all(bind=get_engine())


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
