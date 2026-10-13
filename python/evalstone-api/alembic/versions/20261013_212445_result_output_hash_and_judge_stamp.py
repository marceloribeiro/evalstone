"""result output hash and judge stamp

Revision ID: 128055616334
Revises: 7d8ecf4365fe
Create Date: 2026-10-13 21:24:45.941306+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "128055616334"
down_revision: str | None = "7d8ecf4365fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill() -> None:
    """Existing rows: hash the stored output with the library (what labels are keyed by) and
    copy the judge stamp out of score raw."""
    import json

    from evalstone.checks.human import output_hash
    from evalstone.output import Output

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, output, raw FROM run_results")).all()
    for rid, output, raw in rows:
        output = output if isinstance(output, dict) else json.loads(output)
        raw = raw if isinstance(raw, dict) or raw is None else json.loads(raw)
        jv = raw.get("judge_version") if isinstance(raw, dict) else None
        model = raw.get("model") if isinstance(raw, dict) else None
        conn.execute(
            sa.text(
                "UPDATE run_results SET output_hash = :h, judge_version = :jv, judge_model = :m "
                "WHERE id = :id"
            ),
            {
                "h": output_hash(Output.model_validate(output)),
                "jv": str(jv)[:16] if isinstance(jv, str) and jv else None,
                "m": str(model)[:200] if isinstance(model, str) and model else None,
                "id": rid,
            },
        )


def upgrade() -> None:
    op.add_column("run_results", sa.Column("output_hash", sa.String(length=16), nullable=True))
    op.add_column("run_results", sa.Column("judge_version", sa.String(length=16), nullable=True))
    op.add_column("run_results", sa.Column("judge_model", sa.String(length=200), nullable=True))
    _backfill()
    op.alter_column("run_results", "output_hash", nullable=False)
    op.create_index(
        "ix_results_check_judge_version",
        "run_results",
        ["check_key", "judge_version"],
        unique=False,
    )
    op.create_index(
        "ix_results_sample_output", "run_results", ["sample_key", "output_hash"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_results_sample_output", table_name="run_results")
    op.drop_index("ix_results_check_judge_version", table_name="run_results")
    op.drop_column("run_results", "judge_model")
    op.drop_column("run_results", "judge_version")
    op.drop_column("run_results", "output_hash")
