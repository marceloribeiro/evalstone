"""The model-call proxy: the library's `Providers.complete()` executed inside the center.

An attached library never holds a provider key. It sends the canonical request (system,
messages, max_tokens) and either an explicit `<provider>/<model>` or the `check_key` it is
judging; the center resolves the model from the project's judge settings, decrypts the
org's key in-process, makes the call through the library's own adapter, meters it, and
returns the library's `ChatResponse`.
"""

from __future__ import annotations

from typing import Any

from evalstone._json import canonical
from evalstone.providers import ChatMessage, ChatResponse, ProviderError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import DomainError, Invalid
from app.models import ModelCall, Project, Provider, User
from app.services import judge_settings as judge_svc
from app.services import providers as provider_svc

MAX_REQUEST_BYTES = 512 * 1024  # canonical JSON of system + messages
MAX_OUTPUT_TOKENS = 4096  # verdicts are short; a target call is not what this proxy is for


class UpstreamError(DomainError):
    """The provider call failed (HTTP error, refusal, malformed response)."""

    status = 502


def resolve_model(
    db: Session, project: Project, *, model: str | None, check_key: str | None
) -> str:
    """`<provider>/<model>`: the explicit one, else the project's judge settings for the check."""
    if model:
        name, sep, bare = model.partition("/")
        if not sep or not name or not bare:
            raise Invalid(f"model must be '<provider>/<model>', got {model!r}")
        return model
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
    name = model.partition("/")[0]
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
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float | None,
) -> ChatResponse:
    if max_tokens > MAX_OUTPUT_TOKENS:
        raise Invalid(f"max_tokens is capped at {MAX_OUTPUT_TOKENS} on the proxy")
    size = len(canonical({"system": system, "messages": messages}).encode())
    if size > MAX_REQUEST_BYTES:
        raise Invalid(f"request is {size} bytes; the limit is {MAX_REQUEST_BYTES}")
    resolved = resolve_model(db, project, model=model, check_key=check_key)
    provider = _provider_for(db, project, resolved)
    registry = provider_svc.build_registry([provider])
    request = {
        "system": system,
        "messages": [ChatMessage.model_validate(m) for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    call = ModelCall(
        project_id=project.id,
        provider_name=provider.name,
        model=resolved.partition("/")[2],
        check_key=check_key,
        ok=False,
        caller_user_id=caller.id if caller else None,
    )
    try:
        resp = registry.complete(resolved, request)
    except ProviderError as err:
        call.error = str(err)[:1000]
        db.add(call)
        db.commit()
        raise UpstreamError(f"provider '{provider.name}' failed: {str(err)[:500]}") from err
    finally:
        registry.close()
    call.ok = True
    call.input_tokens, call.output_tokens = resp.input_tokens, resp.output_tokens
    call.cost_usd, call.latency_ms = resp.cost_usd, resp.latency_ms
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


def usage(db: Session, project: Project) -> dict[str, Any]:
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
    return {
        "calls": row[0],
        "failed": row[1],
        "input_tokens": int(row[2]),
        "output_tokens": int(row[3]),
        "cost_usd": float(row[4]),
        "unpriced_calls": row[5],
    }
