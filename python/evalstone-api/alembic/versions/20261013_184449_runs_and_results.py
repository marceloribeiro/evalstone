"""runs and results

Revision ID: 425958d89662
Revises: 8c3bfc89a76d
Create Date: 2026-10-13 18:44:49.936571+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "425958d89662"
down_revision: str | None = "8c3bfc89a76d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("client_run_id", sa.String(length=64), nullable=False),
        sa.Column("suite", sa.String(length=200), nullable=False),
        sa.Column("dataset_name", sa.String(length=200), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("dataset_version_id", sa.UUID(), nullable=True),
        sa.Column("target", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("check_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("baseline_run_id", sa.UUID(), nullable=True),
        sa.Column("client_baseline_run_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("mean_score", sa.Float(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("gate_passed", sa.Boolean(), nullable=True),
        sa.Column("gate_lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_baseline", sa.Boolean(), nullable=False),
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
            ["baseline_run_id"],
            ["runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_project_id"), "runs", ["project_id"], unique=False)
    op.create_index(
        "ix_runs_project_suite_started", "runs", ["project_id", "suite", "started_at"], unique=False
    )
    op.create_index(
        "uq_run_project_client_id", "runs", ["project_id", "client_run_id"], unique=True
    )
    op.create_table(
        "run_results",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("sample_key", sa.String(length=200), nullable=False),
        sa.Column("check_key", sa.String(length=200), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=False),
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
            ["run_id"],
            ["runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_results_run_check_passed",
        "run_results",
        ["run_id", "check_key", "passed"],
        unique=False,
    )
    op.create_index(op.f("ix_run_results_run_id"), "run_results", ["run_id"], unique=False)
    op.create_index(
        "uq_result_run_sample_check",
        "run_results",
        ["run_id", "sample_key", "check_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_result_run_sample_check", table_name="run_results")
    op.drop_index(op.f("ix_run_results_run_id"), table_name="run_results")
    op.drop_index("ix_results_run_check_passed", table_name="run_results")
    op.drop_table("run_results")
    op.drop_index("uq_run_project_client_id", table_name="runs")
    op.drop_index("ix_runs_project_suite_started", table_name="runs")
    op.drop_index(op.f("ix_runs_project_id"), table_name="runs")
    op.drop_table("runs")
