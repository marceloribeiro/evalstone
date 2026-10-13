"""judge cache and labels

Revision ID: c8728e522288
Revises: 425958d89662
Create Date: 2026-10-13 19:00:39.061482+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8728e522288"
down_revision: str | None = "425958d89662"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judge_cache",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("judge_version", sa.String(length=16), nullable=True),
        sa.Column("score", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "cache_key", name="uq_judge_cache_key"),
    )
    op.create_index(op.f("ix_judge_cache_project_id"), "judge_cache", ["project_id"], unique=False)
    op.create_table(
        "labels",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("sample_key", sa.String(length=200), nullable=False),
        sa.Column("output_hash", sa.String(length=16), nullable=False),
        sa.Column("check_key", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("labeler", sa.String(length=200), nullable=False),
        sa.Column("labeler_user_id", sa.UUID(), nullable=True),
        sa.Column("labeled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["labeler_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "sample_key", "output_hash", "check_key", name="uq_label_sample_output"
        ),
    )
    op.create_index(op.f("ix_labels_project_id"), "labels", ["project_id"], unique=False)
    op.create_index(op.f("ix_labels_sample_key"), "labels", ["sample_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_labels_sample_key"), table_name="labels")
    op.drop_index(op.f("ix_labels_project_id"), table_name="labels")
    op.drop_table("labels")
    op.drop_index(op.f("ix_judge_cache_project_id"), table_name="judge_cache")
    op.drop_table("judge_cache")
