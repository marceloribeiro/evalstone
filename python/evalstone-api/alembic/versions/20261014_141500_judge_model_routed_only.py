"""run_results.judge_model holds only the routed <provider>/<model>

Revision ID: 7c3e9a2f4b18
Revises: 1d1798466e64
Create Date: 2026-10-14 14:15:00.000000+00:00

Before lib 0.2.3 the column was stamped from `raw.model`, the provider-reported id, which
judge settings cannot route (Promote was refused). Re-stamp every judge verdict from the
stored `raw.judge_model`; rows from older libraries become NULL.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7c3e9a2f4b18"
down_revision: str | None = "1d1798466e64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE run_results
           SET judge_model = CASE
                 WHEN jsonb_typeof(raw -> 'judge_model') = 'string' AND raw ->> 'judge_model' <> ''
                 THEN left(raw ->> 'judge_model', 200)
               END
         WHERE judge_version IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE run_results
           SET judge_model = CASE
                 WHEN jsonb_typeof(raw -> 'model') = 'string' AND raw ->> 'model' <> ''
                 THEN left(raw ->> 'model', 200)
               END
         WHERE judge_version IS NOT NULL
        """
    )
