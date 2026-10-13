"""label queues

Revision ID: 2c2d5f92bbeb
Revises: 22e7be158158
Create Date: 2026-10-13 20:50:10.692896+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2c2d5f92bbeb"
down_revision: str | None = "22e7be158158"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "label_queues",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("check_key", sa.String(length=200), nullable=False),
        sa.Column("scale", sa.Integer(), nullable=False),
        sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_count", sa.Integer(), nullable=False),
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
        op.f("ix_label_queues_project_id"), "label_queues", ["project_id"], unique=False
    )
    op.create_table(
        "label_tasks",
        sa.Column("queue_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sample_key", sa.String(length=200), nullable=False),
        sa.Column("output_hash", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("assignee_user_id", sa.UUID(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label_id", sa.UUID(), nullable=True),
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
            ["assignee_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["labels.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["queue_id"],
            ["label_queues.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("queue_id", "position", name="uq_task_queue_position"),
    )
    op.create_index(
        "ix_tasks_queue_status_assignee",
        "label_tasks",
        ["queue_id", "status", "assignee_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_queue_status_assignee", table_name="label_tasks")
    op.drop_table("label_tasks")
    op.drop_index(op.f("ix_label_queues_project_id"), table_name="label_queues")
    op.drop_table("label_queues")
