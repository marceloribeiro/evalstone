"""Production monitoring: traces in, sampled scoring on a schedule, windowed alerts out.

Traces arrive with the project's ingest key. A monitor names org-catalog checks and a
sample rate; every minute the beat enqueues `score_monitor` per active monitor, which scores
the unscored traces whose stable `sample_bucket` falls under the rate — deterministic
checks in-process, judges through the center registry with the org's own keys — then
evaluates the alert policy over the window and notifies the webhook on a new breach.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from evalstone._json import canonical
from evalstone.config import FACTORIES
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.score import Context
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import Invalid, NotFound
from app.models import Alert, CheckDefinition, Monitor, Project, Trace, TraceScore, User
from app.services import judge_settings as judge_svc
from app.services import providers as provider_svc
from app.services.catalog import get_by_key
from app.services.providers import validate_base_url
from app.services.runs import output_hash_of

MAX_TRACES_PER_PUSH = 1000
MAX_TRACE_BYTES = 64 * 1024
MAX_TRACES_PER_SCORING = 200  # per monitor per tick; the rest waits for the next minute
WEBHOOK_TIMEOUT_S = 5.0
METRICS = ("pass_rate", "mean_score")


def sample_bucket(project_id: uuid.UUID, client_id: str) -> float:
    """A stable 0..1 number per trace, so a 10% monitor always samples the same 10%."""
    digest = hashlib.sha256(f"{project_id}:{client_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


# --- traces -----------------------------------------------------------------------------------


def ingest_traces(db: Session, project: Project, records: list[dict[str, Any]]) -> int:
    """Store traces, once per client id (a retried push is a no-op); returns how many were new."""
    if len(records) > MAX_TRACES_PER_PUSH:
        raise Invalid(f"at most {MAX_TRACES_PER_PUSH} traces per push")
    values = []
    for i, t in enumerate(records):
        size = len(canonical(t).encode())
        if size > MAX_TRACE_BYTES:
            raise Invalid(f"traces[{i}] is {size} bytes; the limit is {MAX_TRACE_BYTES}")
        client_id = str(t.get("id") or uuid.uuid4())
        output = t.get("output")
        values.append(
            {
                "id": uuid.uuid4(),
                "project_id": project.id,
                "client_id": client_id,
                "input": t["input"],
                "output": output,
                "output_hash": output_hash_of({"value": output}),
                "metadata": dict(t.get("metadata") or {}),
                "tags": sorted(t.get("tags") or []),
                "model": t.get("model"),
                "latency_ms": t.get("latency_ms"),
                "cost_usd": t.get("cost_usd"),
                "occurred_at": t.get("occurred_at") or datetime.now(UTC),
                "sample_bucket": sample_bucket(project.id, client_id),
            }
        )
    if not values:
        return 0
    stmt = (
        insert(Trace)
        .values(values)
        .on_conflict_do_nothing(
            index_elements=["project_id", "client_id"], index_where=Trace.deleted_at.is_(None)
        )
    )
    stored = len(db.execute(stmt.returning(Trace.id)).all())  # psycopg3 reports -1 for rowcount
    db.commit()
    return stored


def list_traces(
    db: Session,
    project: Project,
    *,
    since: datetime | None = None,
    flagged: bool | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[Trace], int]:
    q = select(Trace).where(Trace.project_id == project.id, Trace.deleted_at.is_(None))
    if since is not None:
        q = q.where(Trace.occurred_at >= since)
    if flagged is not None:
        q = q.where(Trace.flagged.is_(flagged))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(
        db.scalars(
            q.order_by(Trace.occurred_at.desc(), Trace.id.desc()).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def get_trace(db: Session, project: Project, trace_id: uuid.UUID) -> Trace:
    t = db.get(Trace, trace_id)
    if t is None or t.deleted_at is not None or t.project_id != project.id:
        raise NotFound("trace not found")
    return t


def flag_trace(db: Session, trace: Trace, *, flagged: bool) -> Trace:
    trace.flagged = flagged
    db.commit()
    db.refresh(trace)
    return trace


# --- monitors ---------------------------------------------------------------------------------


def _validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    metric = policy.get("metric", "pass_rate")
    if metric not in METRICS:
        raise Invalid(f"alert_policy.metric must be one of {', '.join(METRICS)}")
    threshold = policy.get("threshold")
    if not isinstance(threshold, int | float) or not 0.0 <= float(threshold) <= 1.0:
        raise Invalid("alert_policy.threshold must be a number in 0..1")
    window = policy.get("window_minutes", 60)
    if not isinstance(window, int) or isinstance(window, bool) or not 1 <= window <= 7 * 24 * 60:
        raise Invalid("alert_policy.window_minutes must be an integer in 1..10080")
    min_n = policy.get("min_n", 20)
    if not isinstance(min_n, int) or isinstance(min_n, bool) or min_n < 1:
        raise Invalid("alert_policy.min_n must be a positive integer")
    return {
        "metric": metric,
        "threshold": float(threshold),
        "window_minutes": window,
        "min_n": min_n,
    }


def _validate_checks(db: Session, project: Project, keys: list[str]) -> list[str]:
    if not keys:
        raise Invalid("a monitor needs at least one check")
    missing = [k for k in keys if get_by_key(db, project.organization_id, k) is None]
    if missing:
        raise Invalid(f"not in the organization's check catalog: {', '.join(missing)}")
    return list(dict.fromkeys(keys))


def create_monitor(
    db: Session,
    *,
    project: Project,
    name: str,
    check_keys: list[str],
    sample_rate: float,
    alert_policy: dict[str, Any],
    webhook_url: str | None,
    created_by: User | None,
) -> Monitor:
    m = Monitor(
        project_id=project.id,
        name=name,
        check_keys=_validate_checks(db, project, check_keys),
        sample_rate=sample_rate,
        alert_policy=_validate_policy(alert_policy),
        webhook_url=validate_base_url(webhook_url) if webhook_url else None,
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def update_monitor(db: Session, project: Project, m: Monitor, **fields: Any) -> Monitor:
    if "check_keys" in fields and fields["check_keys"] is not None:
        m.check_keys = _validate_checks(db, project, fields["check_keys"])
    if "alert_policy" in fields and fields["alert_policy"] is not None:
        m.alert_policy = _validate_policy(fields["alert_policy"])
    if "webhook_url" in fields:
        m.webhook_url = validate_base_url(fields["webhook_url"]) if fields["webhook_url"] else None
    for k in ("name", "sample_rate", "status"):
        if fields.get(k) is not None:
            setattr(m, k, fields[k])
    db.commit()
    db.refresh(m)
    return m


def list_monitors(db: Session, project: Project) -> list[Monitor]:
    return list(
        db.scalars(
            select(Monitor)
            .where(Monitor.project_id == project.id, Monitor.deleted_at.is_(None))
            .order_by(Monitor.created_at)
        ).all()
    )


def get_monitor(db: Session, project: Project, monitor_id: uuid.UUID) -> Monitor:
    m = db.get(Monitor, monitor_id)
    if m is None or m.deleted_at is not None or m.project_id != project.id:
        raise NotFound("monitor not found")
    return m


def soft_delete_monitor(db: Session, m: Monitor) -> None:
    m.deleted_at = datetime.now(UTC)
    db.commit()


# --- scoring (the Celery body) ----------------------------------------------------------------


def _build_checks(db: Session, project: Project, keys: list[str]) -> dict[str, Any]:
    """The org's catalog definitions → library checks (the same factories the CLI uses)."""
    checks = {}
    for key in keys:
        d: CheckDefinition | None = get_by_key(db, project.organization_id, key)
        if d is None:
            raise Invalid(f"check {key!r} is no longer in the catalog")
        checks[key] = FACTORIES[d.type](key=key, **d.params)
    return checks


def _context(db: Session, project: Project) -> Context:
    """Judges score with the org's providers, in-process, keys decrypted here only."""
    from app.models import Organization
    from app.services.providers import list_providers

    org = db.get(Organization, project.organization_id)
    settings = judge_svc.get_or_default(db, project)
    registry = provider_svc.build_registry(
        list_providers(db, org), default_model=settings.default_model
    )
    return Context(providers=registry, extra={"judge_models": dict(settings.overrides or {})})


def score_monitor(db: Session, monitor_id: uuid.UUID) -> dict[str, Any]:
    """Score up to MAX_TRACES_PER_SCORING unscored sampled traces, then evaluate the policy."""
    m = db.get(Monitor, monitor_id)
    if m is None or m.deleted_at is not None or m.status != "active":
        return {"scored": 0, "skipped": "inactive"}
    project = db.get(Project, m.project_id)
    scored_ids = select(TraceScore.trace_id).where(TraceScore.monitor_id == m.id)
    traces = list(
        db.scalars(
            select(Trace)
            .where(
                Trace.project_id == m.project_id,
                Trace.deleted_at.is_(None),
                Trace.sample_bucket < m.sample_rate,
                Trace.id.not_in(scored_ids),
            )
            .order_by(Trace.occurred_at)
            .limit(MAX_TRACES_PER_SCORING)
        ).all()
    )
    result = {"scored": 0, "errors": 0, "cost_usd": 0.0, "alert": None}
    if traces:
        try:
            checks = _build_checks(db, project, list(m.check_keys))
            ctx = _context(db, project)
        except Exception as exc:
            m.last_error = f"{type(exc).__name__}: {str(exc)[:900]}"
            db.commit()
            return {**result, "skipped": m.last_error}
        now = datetime.now(UTC)
        try:
            for t in traces:
                sample = Sample(id=t.client_id, input=t.input, metadata=dict(t.metadata_ or {}))
                output = Output(value=t.output, model=t.model)
                for key, check in checks.items():
                    s = check.evaluate(sample, output, ctx)
                    db.add(
                        TraceScore(
                            monitor_id=m.id,
                            trace_id=t.id,
                            check_key=key,
                            score=s.value,
                            passed=s.passed,
                            reason=s.reason,
                            error=s.error,
                            cost_usd=s.cost_usd,
                            latency_ms=s.latency_ms,
                            scored_at=now,
                        )
                    )
                    result["cost_usd"] += s.cost_usd or 0.0
                    result["errors"] += 1 if s.error else 0
                result["scored"] += 1
        finally:
            close = getattr(ctx.providers, "close", None)
            if callable(close):
                close()
        m.last_scored_at, m.last_error = now, None
        db.commit()
    result["alert"] = evaluate_policy(db, m)
    return result


def window_metrics(db: Session, m: Monitor) -> dict[str, Any]:
    policy = m.alert_policy
    since = datetime.now(UTC) - timedelta(minutes=policy["window_minutes"])
    row = db.execute(
        select(
            func.count(func.distinct(TraceScore.trace_id)),
            func.avg(case((TraceScore.passed, 1.0), else_=0.0)),
            func.avg(TraceScore.score),
        ).where(
            TraceScore.monitor_id == m.id,
            TraceScore.scored_at >= since,
            TraceScore.error.is_(None),
        )
    ).one()
    n = int(row[0] or 0)
    return {
        "n": n,
        "pass_rate": float(row[1]) if row[1] is not None else None,
        "mean_score": float(row[2]) if row[2] is not None else None,
        "window_minutes": policy["window_minutes"],
    }


def open_alert(db: Session, m: Monitor) -> Alert | None:
    return db.scalar(
        select(Alert).where(Alert.monitor_id == m.id, Alert.resolved_at.is_(None)).limit(1)
    )


def evaluate_policy(db: Session, m: Monitor) -> dict[str, Any] | None:
    """Below the threshold with enough samples → open + notify one alert; recovered → resolve."""
    policy = m.alert_policy
    metrics = window_metrics(db, m)
    value = metrics[policy["metric"]]
    current = open_alert(db, m)
    if metrics["n"] < policy["min_n"] or value is None:
        return None
    if value < policy["threshold"]:
        if current is not None:
            return {"alert_id": str(current.id), "state": "open", "value": value}
        alert = Alert(
            monitor_id=m.id,
            project_id=m.project_id,
            metric=policy["metric"],
            value=value,
            threshold=policy["threshold"],
            n=metrics["n"],
            window_minutes=policy["window_minutes"],
            opened_at=datetime.now(UTC),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        notify(db, m, alert)
        return {"alert_id": str(alert.id), "state": "opened", "value": value}
    if current is not None:
        current.resolved_at = datetime.now(UTC)
        db.commit()
        return {"alert_id": str(current.id), "state": "resolved", "value": value}
    return None


def notify(db: Session, m: Monitor, alert: Alert) -> None:
    """POST the alert to the monitor's webhook (SSRF-guarded at save time); failures recorded."""
    if not m.webhook_url:
        return
    payload = {
        "event": "evalstone.alert.opened",
        "alert_id": str(alert.id),
        "monitor": {"id": str(m.id), "name": m.name},
        "project_id": str(m.project_id),
        "metric": alert.metric,
        "value": alert.value,
        "threshold": alert.threshold,
        "n": alert.n,
        "window_minutes": alert.window_minutes,
        "opened_at": alert.opened_at.isoformat(),
    }
    try:
        resp = httpx.post(m.webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT_S)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        alert.notified_at = datetime.now(UTC)
    except Exception as exc:
        alert.notify_error = f"{type(exc).__name__}: {str(exc)[:500]}"
    db.commit()


def list_alerts(db: Session, project: Project, *, open_only: bool = False) -> list[Alert]:
    q = select(Alert).where(Alert.project_id == project.id)
    if open_only:
        q = q.where(Alert.resolved_at.is_(None))
    return list(db.scalars(q.order_by(Alert.opened_at.desc(), Alert.id.desc()).limit(500)).all())


def active_monitor_ids(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Monitor.id).where(Monitor.status == "active", Monitor.deleted_at.is_(None))
        ).all()
    )
