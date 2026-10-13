"""calibrations

Revision ID: 7d8ecf4365fe
Revises: 2c2d5f92bbeb
Create Date: 2026-10-13 21:15:37.343114+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7d8ecf4365fe"
down_revision: str | None = "2c2d5f92bbeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibrations",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("check_key", sa.String(length=200), nullable=False),
        sa.Column("judge_version", sa.String(length=16), nullable=False),
        sa.Column("label_check", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("agreement", sa.Float(), nullable=True),
        sa.Column("kappa", sa.Float(), nullable=True),
        sa.Column("mean_abs_error", sa.Float(), nullable=True),
        sa.Column("confusion", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
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
            ["created_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_calibrations_project_created",
        "calibrations",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_calibrations_project_created", table_name="calibrations")
    op.drop_table("calibrations")
