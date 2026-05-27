"""add language and twin_song_id to songs

Revision ID: b3f7c1a2d5e8
Revises: 9b2e61d3a4f0
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f7c1a2d5e8"
down_revision: Union[str, Sequence[str], None] = "9b2e61d3a4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "songs",
        sa.Column("language", sa.String(length=10), server_default="tr", nullable=False),
    )
    op.add_column(
        "songs",
        sa.Column("twin_song_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("songs", "twin_song_id")
    op.drop_column("songs", "language")
