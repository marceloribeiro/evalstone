"""The check catalog: the library's built-in check types, and an org's own named checks.

Built-ins are introspected from the installed `evalstone` library (`FACTORIES`), so the
catalog is exactly the library version the center runs. Org checks are a type + params
the library's factory accepts; every change becomes an immutable version.
"""

from __future__ import annotations

import inspect
import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import evalstone
from evalstone._json import canonical, sha256
from evalstone.checks.deterministic import _MISSING
from evalstone.config import FACTORIES
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, Invalid, NotFound
from app.models import CheckDefinition, CheckVersion, Organization, User

_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,199}$")
MAX_PARAMS_BYTES = 64 * 1024
# What the library reports as `check.kind` per family (rag checks ARE judges — they call a
# model — so the library tags them `judge`); plain names are deterministic.
_KIND_BY_FAMILY = {"rag": "judge", "safety": "safety", "trajectory": "trajectory"}
_KIND_BY_FAMILY["comparison"] = "comparison"
_KIND_BY_TYPE = {"judge": "judge", "human": "human"}


def kind_of(check_type: str) -> str:
    if check_type in _KIND_BY_TYPE:
        return _KIND_BY_TYPE[check_type]
    family, sep, _ = check_type.partition(".")
    return _KIND_BY_FAMILY.get(family, "deterministic") if sep else "deterministic"


def _machine_bound(annotation: str) -> str | None:
    """Why a parameter's value lives on a machine, by annotation: a callable, a file path, or
    a target. `Target | Mapping` (pairwise `baseline`) is storable as a plain mapping."""
    if "Callable" in annotation:
        return "callable"
    if "Path" in annotation:
        return "path"
    if "Target" in annotation:
        return "target"
    return None


def _params_of(fn: Any) -> list[dict[str, Any]]:
    out = []
    for p in inspect.signature(fn).parameters.values():
        if p.name == "key" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        # `_MISSING` means "falls back to sample.expected" — the library's own sentinel
        required = p.default is p.empty or p.default is _MISSING
        annotation = "" if p.annotation is p.empty else str(p.annotation)
        out.append(
            {
                "name": p.name,
                "required": required,
                "default": None if required else _jsonable(p.default),
                "annotation": annotation,
                "machine_bound": _machine_bound(annotation),
            }
        )
    return out


def _jsonable(value: Any) -> Any:
    try:
        canonical(value)
        return value
    except TypeError:
        return repr(value)


@lru_cache
def builtins() -> list[dict[str, Any]]:
    """Every library check type with its kind, parameters and docstring summary."""
    rows = []
    for name, fn in sorted(FACTORIES.items()):
        doc = (inspect.getdoc(fn) or "").strip().split("\n\n")[0].replace("\n", " ")
        params = _params_of(fn)
        rows.append(
            {
                "type": name,
                "kind": kind_of(name),
                "params": params,
                "summary": doc[:300],
                "library_version": evalstone.__version__,
                # storable unless a REQUIRED param can only be a callable or a file
                "storable": not any(
                    p["required"] and p["machine_bound"] in ("callable", "path") for p in params
                ),
            }
        )
    return rows


def _check_machine_bound(check_type: str, fn: Any, params: dict[str, Any]) -> None:
    """Refuse values the center cannot hold: callables, file paths, target specs."""
    sig = inspect.signature(fn).parameters
    for name, value in params.items():
        if name not in sig:
            continue  # the bind below reports unknown params
        ann = "" if sig[name].annotation is inspect.Parameter.empty else str(sig[name].annotation)
        why = _machine_bound(ann)
        if why == "callable" and value is not None:
            raise Invalid(f"{check_type}.{name} is a Python callable; it cannot be stored")
        if why == "path" and value != "center":
            raise Invalid(f"{check_type}.{name} is a file on a machine; only 'center' is storable")
        if why == "target" and isinstance(value, dict) and "kind" in value:
            raise Invalid(
                f"{check_type}.{name} is a target spec (runs code on a machine); give a plain "
                "{sample_id: output} mapping instead"
            )


def validate_spec(check_type: str, params: dict[str, Any]) -> dict[str, Any]:
    """The spec the library would accept: a known type whose factory binds these params.

    Binding only (no factory is executed): a server-side spec must not need files or code.
    """
    fn = FACTORIES.get(check_type)
    if fn is None:
        raise Invalid(f"unknown check type {check_type!r} (known: {', '.join(sorted(FACTORIES))})")
    _check_machine_bound(check_type, fn, params)
    if "key" in params:
        raise Invalid("`key` is the definition's key, not a param")
    size = len(canonical(params).encode())
    if size > MAX_PARAMS_BYTES:
        raise Invalid(f"params are {size} bytes; the limit is {MAX_PARAMS_BYTES}")
    try:
        inspect.signature(fn).bind(key="x", **params)
    except TypeError as err:
        raise Invalid(f"params do not fit {check_type}: {err}") from err
    return params


def content_hash(check_type: str, params: dict[str, Any]) -> str:
    return sha256({"type": check_type, "params": params})


# --- org checks ------------------------------------------------------------------------------


def list_checks(db: Session, org: Organization) -> list[CheckDefinition]:
    return list(
        db.scalars(
            select(CheckDefinition)
            .where(CheckDefinition.organization_id == org.id, CheckDefinition.deleted_at.is_(None))
            .order_by(CheckDefinition.key)
        ).all()
    )


def get_check(db: Session, org: Organization, check_id: uuid.UUID) -> CheckDefinition:
    row = db.get(CheckDefinition, check_id)
    if row is None or row.deleted_at is not None or row.organization_id != org.id:
        raise NotFound("check not found")
    return row


def get_by_key(db: Session, org_id: uuid.UUID, key: str) -> CheckDefinition | None:
    return db.scalar(
        select(CheckDefinition).where(
            CheckDefinition.organization_id == org_id,
            CheckDefinition.key == key,
            CheckDefinition.deleted_at.is_(None),
        )
    )


def _snapshot(
    db: Session, row: CheckDefinition, *, version: int, note: str, by: User | None
) -> CheckVersion:
    v = CheckVersion(
        check_definition_id=row.id,
        version=version,
        type=row.type,
        params=dict(row.params),
        content_hash=content_hash(row.type, row.params),
        note=note,
        created_by_user_id=by.id if by else None,
    )
    db.add(v)
    return v


def create(
    db: Session,
    *,
    org: Organization,
    key: str,
    check_type: str,
    params: dict[str, Any],
    description: str = "",
    created_by: User | None,
) -> CheckDefinition:
    if not _KEY.match(key):
        raise Invalid("key must be lowercase letters, digits, '.', '_' or '-' (max 200)")
    params = validate_spec(check_type, params)
    if get_by_key(db, org.id, key) is not None:
        raise Conflict(f"check '{key}' already exists in this organization")
    row = CheckDefinition(
        organization_id=org.id,
        key=key,
        type=check_type,
        kind=kind_of(check_type),
        params=params,
        description=description,
        current_version=1,
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(row)
    db.flush()
    _snapshot(db, row, version=1, note="created", by=created_by)
    db.commit()
    db.refresh(row)
    return row


def update(
    db: Session,
    row: CheckDefinition,
    *,
    check_type: str | None,
    params: dict[str, Any] | None,
    description: str | None,
    note: str,
    by: User | None,
) -> tuple[CheckDefinition, bool]:
    """Description edits are in place; a type/params change becomes the next version.

    The row is locked FOR UPDATE and re-read before deciding, so two concurrent edits
    serialise into consecutive versions instead of racing on the version number.
    """
    db.execute(select(CheckDefinition.id).where(CheckDefinition.id == row.id).with_for_update())
    db.refresh(row)
    new_type = check_type or row.type
    new_params = validate_spec(new_type, params if params is not None else dict(row.params))
    if description is not None:
        row.description = description
    changed = content_hash(new_type, new_params) != content_hash(row.type, row.params)
    if note and not changed:
        db.rollback()
        raise Invalid("a note accompanies a type/params change; nothing changed")
    if changed:
        row.type, row.kind, row.params = new_type, kind_of(new_type), new_params
        row.current_version += 1
        _snapshot(db, row, version=row.current_version, note=note, by=by)
    db.commit()
    db.refresh(row)
    return row, changed


def list_versions(db: Session, row: CheckDefinition) -> list[CheckVersion]:
    return list(
        db.scalars(
            select(CheckVersion)
            .where(CheckVersion.check_definition_id == row.id)
            .order_by(CheckVersion.version)
        ).all()
    )


def get_version(db: Session, row: CheckDefinition, version: int) -> CheckVersion:
    v = db.scalar(
        select(CheckVersion).where(
            CheckVersion.check_definition_id == row.id, CheckVersion.version == version
        )
    )
    if v is None:
        raise NotFound("check version not found")
    return v


def soft_delete(db: Session, row: CheckDefinition) -> None:
    row.deleted_at = datetime.now(UTC)
    db.commit()


def as_yaml_spec(rows: list[CheckDefinition]) -> dict[str, dict[str, Any]]:
    """The org's checks as the `checks:` block of an evalstone.yaml."""
    return {r.key: {"type": r.type, **r.params} for r in rows}
