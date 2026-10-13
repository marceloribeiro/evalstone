"""monitoring

Revision ID: e5d47bd14ebc
Revises: 128055616334
Create Date: 2026-10-13 21:35:58.333735+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5d47bd14ebc"
down_revision: str | None = "128055616334"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitors",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("check_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sample_rate", sa.Float(), nullable=False),
        sa.Column("alert_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
    op.create_index(op.f("ix_monitors_project_id"), "monitors", ["project_id"], unique=False)
    op.create_table(
        "traces",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_hash", sa.String(length=16), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.Column("sample_bucket", sa.Float(), nullable=False),
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
    )
    op.create_index(
        "ix_traces_project_occurred", "traces", ["project_id", "occurred_at"], unique=False
    )
    op.create_index(
        "uq_trace_project_client_id_live", "traces", ["project_id", "client_id"], unique=True
    )
    op.create_table(
        "alerts",
        sa.Column("monitor_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(length=30), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_error", sa.Text(), nullable=True),
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
            ["monitor_id"],
            ["monitors.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_monitor_opened", "alerts", ["monitor_id", "opened_at"], unique=False)
    op.create_index(op.f("ix_alerts_project_id"), "alerts", ["project_id"], unique=False)
    op.create_table(
        "trace_scores",
        sa.Column("monitor_id", sa.UUID(), nullable=False),
        sa.Column("trace_id", sa.UUID(), nullable=False),
        sa.Column("check_key", sa.String(length=200), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
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
            ["monitor_id"],
            ["monitors.id"],
        ),
        sa.ForeignKeyConstraint(
            ["trace_id"],
            ["traces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trace_scores_monitor_scored", "trace_scores", ["monitor_id", "scored_at"], unique=False
    )
    op.create_index(op.f("ix_trace_scores_trace_id"), "trace_scores", ["trace_id"], unique=False)
    op.create_index(
        "uq_trace_score", "trace_scores", ["monitor_id", "trace_id", "check_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_trace_score", table_name="trace_scores")
    op.drop_index(op.f("ix_trace_scores_trace_id"), table_name="trace_scores")
    op.drop_index("ix_trace_scores_monitor_scored", table_name="trace_scores")
    op.drop_table("trace_scores")
    op.drop_index(op.f("ix_alerts_project_id"), table_name="alerts")
    op.drop_index("ix_alerts_monitor_opened", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("uq_trace_project_client_id_live", table_name="traces")
    op.drop_index("ix_traces_project_occurred", table_name="traces")
    op.drop_table("traces")
    op.drop_index(op.f("ix_monitors_project_id"), table_name="monitors")
    op.drop_table("monitors")
