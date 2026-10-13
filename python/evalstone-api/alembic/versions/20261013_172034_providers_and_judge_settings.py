"""providers and judge settings

Revision ID: 7642ac8a9c83
Revises: 84615fb799fd
Create Date: 2026-10-13 17:20:34.340495+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7642ac8a9c83"
down_revision: str | None = "84615fb799fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("adapter", sa.String(length=20), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("key_last4", sa.String(length=4), nullable=True),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeout_s", sa.Float(), nullable=False),
        sa.Column("max_tokens_param", sa.String(length=30), nullable=True),
        sa.Column("verified_ok", sa.Boolean(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_providers_organization_id"), "providers", ["organization_id"], unique=False
    )
    op.create_index(
        "uq_provider_org_name_live",
        "providers",
        ["organization_id", "name"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )
    op.create_table(
        "judge_settings",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("default_model", sa.String(length=200), nullable=True),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.UniqueConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("judge_settings")
    op.drop_index(
        "uq_provider_org_name_live", table_name="providers", postgresql_where="deleted_at IS NULL"
    )
    op.drop_index(op.f("ix_providers_organization_id"), table_name="providers")
    op.drop_table("providers")
