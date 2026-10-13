"""trace scores attempts and partial trace uniqueness

Revision ID: 1d1798466e64
Revises: e5d47bd14ebc
Create Date: 2026-10-13 21:48:29.817952+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1d1798466e64"
down_revision: str | None = "e5d47bd14ebc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trace_scores",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("trace_scores", "attempts", server_default=None)
    # a soft-deleted trace must not block re-ingest of its client id: the unique is on live rows
    op.drop_index("uq_trace_project_client_id_live", table_name="traces")
    op.create_index(
        "uq_trace_project_client_id_live",
        "traces",
        ["project_id", "client_id"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_trace_project_client_id_live", table_name="traces")
    op.create_index(
        "uq_trace_project_client_id_live", "traces", ["project_id", "client_id"], unique=True
    )
    op.drop_column("trace_scores", "attempts")
