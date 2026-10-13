"""The model-call proxy: the library's `Providers.complete()` executed inside the center.

An attached library never holds a provider key. It sends the canonical request (system,
messages, max_tokens) and either an explicit `<provider>/<model>` or the `check_key` it is
judging; the center resolves the model from the project's judge settings, decrypts the
org's key in-process, makes the call through the library's own adapter, meters it, and
returns the library's `ChatResponse`.
"""

from __future__ import annotations

import time

from evalstone._json import canonical
from evalstone.providers import ChatMessage, ChatResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import DomainError, Invalid
from app.models import ModelCall, Project, Provider, User
from app.services import judge_settings as judge_svc
from app.services import providers as provider_svc
from app.services.judge_settings import split_model

MAX_REQUEST_BYTES = 512 * 1024  # canonical JSON of system + messages
MAX_OUTPUT_TOKENS = 4096  # verdicts are short; a target call is not what this proxy is for


class UpstreamError(DomainError):
    """The provider call failed (HTTP error, refusal, malformed response)."""

    status = 502


class Usage(BaseModel):
    """Per-project totals over every metered call (its own endpoint; not paged)."""

    calls: int
    failed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    unpriced_calls: int


def resolve_model(
    db: Session, project: Project, *, model: str | None, check_key: str | None
) -> str:
    """`<provider>/<model>`: the explicit one, else the project's judge settings for the check."""
    if model:
        return "/".join(split_model(model))
    if not check_key:
        raise Invalid("give a model or the check_key to resolve one from the judge settings")
    settings = judge_svc.get_or_default(db, project)
    resolved = judge_svc.model_for(settings, check_key)
    if resolved is None:
        raise Invalid(
            f"no judge model for check {check_key!r}: set the project's judge settings "
            "(default_model or an override) or pass a model"
        )
    return resolved


def _provider_for(db: Session, project: Project, model: str) -> Provider:
    name, _ = split_model(model)
    p = provider_svc.get_by_name(db, project.organization_id, name)
    if p is None:
        raise Invalid(f"no provider named {name!r} in this organization")
    return p


def complete(
    db: Session,
    *,
    project: Project,
    caller: User | None,
    model: str | None,
    check_key: str | None,
    system: str | None,
    messages: list[ChatMessage],
    max_tokens: int,
    temperature: float | None,
) -> ChatResponse:
    """The upstream call runs with NO database transaction open.

    The reads commit (and release the pooled connection) before the provider is dialled —
    a slow judge must not pin a connection for its whole timeout — and the metering row is
    written afterwards in its own short transaction. Anything the adapter raises after the
    key was spent is metered as a failed call and surfaces as a 502.
    """
    size = len(canonical({"system": system, "messages": messages}).encode())
    if size > MAX_REQUEST_BYTES:
        raise Invalid(f"request is {size} bytes; the limit is {MAX_REQUEST_BYTES}")
    resolved = resolve_model(db, project, model=model, check_key=check_key)
    provider = _provider_for(db, project, resolved)
    registry = provider_svc.build_registry([provider])  # decrypts the key now, in-process
    call = ModelCall(
        project_id=project.id,
        provider_name=provider.name,
        model=split_model(resolved)[1],
        check_key=check_key,
        ok=False,
        caller_user_id=caller.id if caller else None,
    )
    db.commit()  # release the read transaction + connection before the slow part
    request = {
        "system": system,
        "messages": list(messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    started = time.perf_counter()
    try:
        resp = registry.complete(resolved, request)
    except Exception as err:  # ProviderError, or a malformed-response crash after the spend
        call.latency_ms = (time.perf_counter() - started) * 1000
        call.error = f"{type(err).__name__}: {str(err)[:900]}"
        db.add(call)
        db.commit()
        raise UpstreamError(f"provider '{provider.name}' failed: {str(err)[:500]}") from err
    finally:
        registry.close()
    call.ok = True
    call.input_tokens, call.output_tokens = resp.input_tokens, resp.output_tokens
    call.cost_usd = resp.cost_usd
    call.latency_ms = resp.latency_ms or (time.perf_counter() - started) * 1000
    db.add(call)
    db.commit()
    return resp


def list_calls(
    db: Session, project: Project, *, offset: int = 0, limit: int = 50
) -> tuple[list[ModelCall], int]:
    q = select(ModelCall).where(ModelCall.project_id == project.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(
        db.scalars(
            q.order_by(ModelCall.created_at.desc(), ModelCall.id.desc()).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def usage(db: Session, project: Project) -> Usage:
    row = db.execute(
        select(
            func.count(),
            func.count().filter(ModelCall.ok.is_(False)),
            func.coalesce(func.sum(ModelCall.input_tokens), 0),
            func.coalesce(func.sum(ModelCall.output_tokens), 0),
            func.coalesce(func.sum(ModelCall.cost_usd), 0.0),
            func.count().filter(ModelCall.ok.is_(True), ModelCall.cost_usd.is_(None)),
        ).where(ModelCall.project_id == project.id)
    ).one()
    return Usage(
        calls=row[0],
        failed=row[1],
        input_tokens=int(row[2]),
        output_tokens=int(row[3]),
        cost_usd=float(row[4]),
        unpriced_calls=row[5],
    )
