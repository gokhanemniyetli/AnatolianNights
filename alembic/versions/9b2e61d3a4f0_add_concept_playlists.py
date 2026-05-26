"""add concept playlists

Revision ID: 9b2e61d3a4f0
Revises: 6e886c7a3826
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b2e61d3a4f0"
down_revision: Union[str, Sequence[str], None] = "6e886c7a3826"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "concept_playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("group", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.String(length=100), nullable=True),
        sa.Column("research", sa.Text(), nullable=True),
        sa.Column("style_profile", sa.Text(), nullable=True),
        sa.Column("anchor_city_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["anchor_city_id"], ["cities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("title"),
    )
    op.create_table(
        "concept_generation_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("concept_playlist_id", sa.Integer(), nullable=False),
        sa.Column("used_themes", sa.Text(), nullable=False),
        sa.Column("used_titles", sa.Text(), nullable=False),
        sa.Column("used_hooks", sa.Text(), nullable=False),
        sa.Column("used_keywords", sa.Text(), nullable=False),
        sa.Column("used_instruments", sa.Text(), nullable=False),
        sa.Column("used_moods", sa.Text(), nullable=False),
        sa.Column("used_tempos", sa.Text(), nullable=False),
        sa.Column("used_style_prompts", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["concept_playlist_id"], ["concept_playlists.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_playlist_id"),
    )
    op.add_column("songs", sa.Column("concept_playlist_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("songs", "concept_playlist_id")
    op.drop_table("concept_generation_history")
    op.drop_table("concept_playlists")
