"""The cross-run judge cache: the library's `ScoreCache` get/set, per project, over HTTP.

Entries are the library's `Score` JSON under the library's own key, so an attached run
reads verdicts another machine (or last night's CI) already paid for.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from evalstone.score import Score
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import Invalid
from app.models import JudgeCacheEntry, Project

_KEY = re.compile(r"^[0-9a-f]{64}$")
MAX_LOOKUP_KEYS = 1000


def validate_key(key: str) -> str:
    if not _KEY.match(key):
        raise Invalid("cache key must be a 64-hex sha256 (the library's cache_key)")
    return key


def _validate_score(score: dict[str, Any]) -> dict[str, Any]:
    try:
        return Score.model_validate(score).model_dump(mode="json")
    except (ValueError, TypeError) as err:
        raise Invalid(f"invalid score: {str(err)[:300]}") from err


def get(db: Session, project: Project, key: str) -> JudgeCacheEntry | None:
    row = db.scalar(
        select(JudgeCacheEntry).where(
            JudgeCacheEntry.project_id == project.id, JudgeCacheEntry.cache_key == validate_key(key)
        )
    )
    if row is not None:
        row.hits += 1
        row.last_hit_at = datetime.now(UTC)
        db.commit()
    return row


def lookup(db: Session, project: Project, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Many keys in one query (a suite warms its cache before judging); hits are not counted."""
    if len(keys) > MAX_LOOKUP_KEYS:
        raise Invalid(f"at most {MAX_LOOKUP_KEYS} keys per lookup")
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
    score: dict[str, Any],
    *,
    judge_version: str | None = None,
) -> tuple[JudgeCacheEntry, bool]:
    """Upsert (race-safe); returns (row, created)."""
    key, score = validate_key(key), _validate_score(score)
    stmt = (
        insert(JudgeCacheEntry)
        .values(
            id=uuid.uuid4(),
            project_id=project.id,
            cache_key=key,
            judge_version=judge_version,
            score=score,
        )
        .on_conflict_do_update(
            index_elements=["project_id", "cache_key"],
            set_={"score": score, "judge_version": judge_version},
        )
        .returning(JudgeCacheEntry.id, text("(xmax = 0)"))  # xmax = 0 ⇔ freshly inserted
    )
    row_id, created = db.execute(stmt).one()
    db.commit()
    return db.get(JudgeCacheEntry, row_id), bool(created)
