"""The cross-run judge cache: the library's `ScoreCache` get/set, per project, over HTTP.

Entries are the library's `Score` JSON under the library's own key, so an attached run
reads verdicts another machine (or last night's CI) already paid for.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from evalstone.score import Score
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import Invalid
from app.models import JudgeCacheEntry, Project

_KEY = re.compile(r"^[0-9a-f]{64}$")
MAX_LOOKUP_KEYS = 1000  # the schema's list cap reads this constant


def validate_key(key: str) -> str:
    if not _KEY.match(key):
        raise Invalid("cache key must be a 64-hex sha256 (the library's cache_key)")
    return key


def get(db: Session, project: Project, key: str) -> JudgeCacheEntry | None:
    """One atomic UPDATE counts the hit (concurrent reads do not lose increments)."""
    row = db.scalar(
        update(JudgeCacheEntry)
        .where(
            JudgeCacheEntry.project_id == project.id, JudgeCacheEntry.cache_key == validate_key(key)
        )
        .values(hits=JudgeCacheEntry.hits + 1, last_hit_at=func.now())
        .returning(JudgeCacheEntry)
    )
    db.commit()
    return row


def lookup(db: Session, project: Project, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Many keys in one query (a suite warms its cache before judging); hits are not counted."""
    keys = [validate_key(k) for k in keys]
    rows = db.scalars(
        select(JudgeCacheEntry).where(
            JudgeCacheEntry.project_id == project.id, JudgeCacheEntry.cache_key.in_(keys)
        )
    ).all()
    return {r.cache_key: r.score for r in rows}


def put(
    db: Session,
    project: Project,
    key: str,
    score: Score,
    *,
    judge_version: str | None = None,
) -> tuple[JudgeCacheEntry, bool]:
    """Upsert (race-safe); returns (row, created). A re-put without a version keeps the old one."""
    key = validate_key(key)
    stmt = insert(JudgeCacheEntry).values(
        id=uuid.uuid4(),
        project_id=project.id,
        cache_key=key,
        judge_version=judge_version,
        score=score.model_dump(mode="json"),
    )
    stmt = (
        stmt.on_conflict_do_update(
            index_elements=["project_id", "cache_key"],
            set_={
                "score": stmt.excluded.score,
                "judge_version": func.coalesce(
                    stmt.excluded.judge_version, JudgeCacheEntry.judge_version
                ),
                "updated_at": func.now(),
            },
        ).returning(JudgeCacheEntry.id, text("(xmax = 0)"))  # xmax = 0 ⇔ freshly inserted
    )
    row_id, created = db.execute(stmt).one()
    db.commit()
    return db.get(JudgeCacheEntry, row_id), bool(created)
