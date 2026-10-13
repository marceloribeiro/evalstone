"""Projects under an organization, and their ingest keys (sha256-stored, shown once)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, Invalid, NotFound
from app.models import IngestKey, Organization, Project, User
from app.security import hash_ingest_key, new_ingest_key

LAST_USED_RESOLUTION = timedelta(seconds=60)  # ingest is the hot path; one stamp per minute

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _SLUG.sub("-", name.lower()).strip("-")[:100]
    if not slug:
        raise Invalid("name must contain a letter or digit")
    return slug


def list_projects(db: Session, org: Organization) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.organization_id == org.id, Project.deleted_at.is_(None))
            .order_by(Project.created_at)
        ).all()
    )


def get_project(db: Session, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.deleted_at is not None:
        raise NotFound("project not found")
    return p


def _slug_taken(db: Session, org_id: uuid.UUID, slug: str, *, except_id: uuid.UUID | None) -> bool:
    q = select(Project.id).where(
        Project.organization_id == org_id, Project.slug == slug, Project.deleted_at.is_(None)
    )
    if except_id is not None:
        q = q.where(Project.id != except_id)
    return db.scalar(q) is not None


def create(
    db: Session, *, org: Organization, name: str, slug: str | None = None, description: str = ""
) -> Project:
    slug = slugify(slug or name)
    if _slug_taken(db, org.id, slug, except_id=None):
        raise Conflict(f"slug '{slug}' already used in this organization")
    p = Project(organization_id=org.id, name=name, slug=slug, description=description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update(db: Session, project: Project, **fields) -> Project:
    if "slug" in fields and fields["slug"] is not None:
        fields["slug"] = slugify(fields["slug"])
        if _slug_taken(db, project.organization_id, fields["slug"], except_id=project.id):
            raise Conflict(f"slug '{fields['slug']}' already used in this organization")
    for k, v in fields.items():
        if v is not None:
            setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return project


def soft_delete(db: Session, project: Project) -> None:
    project.deleted_at = datetime.now(UTC)
    db.commit()


# --- ingest keys -------------------------------------------------------------


def list_ingest_keys(db: Session, project: Project) -> list[IngestKey]:
    return list(
        db.scalars(
            select(IngestKey)
            .where(IngestKey.project_id == project.id, IngestKey.deleted_at.is_(None))
            .order_by(IngestKey.created_at)
        ).all()
    )


def create_ingest_key(
    db: Session, *, project: Project, created_by: User, name: str
) -> tuple[IngestKey, str]:
    """Returns the row and the plaintext secret — the only time the secret exists server-side."""
    secret, key_hash, prefix = new_ingest_key()
    key = IngestKey(
        project_id=project.id,
        name=name,
        key_hash=key_hash,
        prefix=prefix,
        created_by_user_id=created_by.id,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key, secret


def revoke_ingest_key(db: Session, project: Project, key_id: uuid.UUID) -> IngestKey:
    key = db.get(IngestKey, key_id)
    if key is None or key.deleted_at is not None or key.project_id != project.id:
        raise NotFound("ingest key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
        db.refresh(key)
    return key


def resolve_ingest_key(db: Session, secret: str) -> Project | None:
    """The project a secret belongs to, or None (unknown / revoked / deleted). Stamps last use."""
    key = db.scalar(
        select(IngestKey).where(
            IngestKey.key_hash == hash_ingest_key(secret),
            IngestKey.revoked_at.is_(None),
            IngestKey.deleted_at.is_(None),
        )
    )
    if key is None:
        return None
    project = db.get(Project, key.project_id)
    if project is None or project.deleted_at is not None:
        return None
    org = db.get(Organization, project.organization_id)
    if org is None or org.deleted_at is not None:
        return None  # a deleted org's keys stop working even if a project row slipped through
    now = datetime.now(UTC)
    if key.last_used_at is None or now - key.last_used_at > LAST_USED_RESOLUTION:
        key.last_used_at = now
        db.commit()
    return project
