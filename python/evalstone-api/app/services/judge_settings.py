"""Per-project judge model choice: a default and per-check overrides, each `<provider>/<model>`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Invalid
from app.models import JudgeSettings, Project, Provider


def get_or_default(db: Session, project: Project) -> JudgeSettings:
    row = db.scalar(select(JudgeSettings).where(JudgeSettings.project_id == project.id))
    return row or JudgeSettings(project_id=project.id, default_model=None, overrides={})


def _live_provider_names(db: Session, project: Project) -> set[str]:
    return set(
        db.scalars(
            select(Provider.name).where(
                Provider.organization_id == project.organization_id, Provider.deleted_at.is_(None)
            )
        ).all()
    )


MAX_PROVIDER_NAME = 50
MAX_BARE_MODEL = 200  # model_calls.model width


def split_model(model: str, *, where: str = "model") -> tuple[str, str]:
    """`<provider>/<model>` → (provider, bare model); the one format rule for every caller."""
    model = model.strip()
    name, sep, bare = model.partition("/")
    if not sep or not name or not bare:
        raise Invalid(f"{where}: model must be '<provider>/<model>', got {model!r}")
    if len(name) > MAX_PROVIDER_NAME or len(bare) > MAX_BARE_MODEL:
        raise Invalid(f"{where}: provider ≤ {MAX_PROVIDER_NAME} and model ≤ {MAX_BARE_MODEL} chars")
    return name, bare


def _check_model(names: set[str], model: str, *, where: str) -> str:
    name, bare = split_model(model, where=where)
    if name not in names:
        raise Invalid(f"{where}: no provider named {name!r} in this organization")
    return f"{name}/{bare}"


def put(
    db: Session, project: Project, *, default_model: str | None, overrides: dict[str, str]
) -> JudgeSettings:
    row = db.scalar(select(JudgeSettings).where(JudgeSettings.project_id == project.id))
    if row is None:
        row = JudgeSettings(project_id=project.id)
        db.add(row)
    names = _live_provider_names(db, project)  # one query, however many overrides
    row.default_model = (
        _check_model(names, default_model, where="default_model") if default_model else None
    )
    row.overrides = {
        str(k): _check_model(names, v, where=f"overrides[{k!r}]")
        for k, v in (overrides or {}).items()
    }
    db.commit()
    db.refresh(row)
    return row


def model_for(settings: JudgeSettings, check_key: str) -> str | None:
    """The model a check should use: its override, else the project default, else None."""
    return (settings.overrides or {}).get(check_key) or settings.default_model
