"""initial schema

Revision ID: 20260315_0001
Revises:
Create Date: 2026-03-15 21:30:00
"""

from __future__ import annotations

from alembic import op

from markfold.repositories.database import Base
from markfold.repositories import models  # noqa: F401


revision = "20260315_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
