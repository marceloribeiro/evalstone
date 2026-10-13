"""Request-scoped dependencies.

Current user (JWT), org membership + role gate, project context, ingest-key project.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import Forbidden, NotFound, Unauthorized
from app.models import Organization, OrganizationMember, Project, Role, User
from app.security import INGEST_KEY_PREFIX, decode_token
from app.services import organizations as org_service
from app.services import projects as project_service
from app.services import users as user_service

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise Unauthorized("missing bearer token")
    user = user_service.get_user(db, decode_token(credentials.credentials))
    if user is None:
        raise Unauthorized("unknown user")
    return user


@dataclass
class MemberContext:
    user: User
    organization: Organization
    membership: OrganizationMember

    @property
    def role(self) -> Role:
        return self.membership.role


def get_member(
    organization_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    org = org_service.get_organization(db, organization_id)
    membership = org_service.get_membership(db, org.id, user.id)
    if membership is None:
        raise NotFound("organization not found")  # membership is not disclosed to outsiders
    return MemberContext(user=user, organization=org, membership=membership)


def require(min_role: Role):
    """Dependency factory: `Depends(require(Role.ADMIN))`."""

    def _gate(ctx: MemberContext = Depends(get_member)) -> MemberContext:
        if not ctx.role.at_least(min_role):
            raise Forbidden(f"requires role {min_role.value} or higher")
        return ctx

    return _gate


@dataclass
class ProjectContext(MemberContext):
    project: Project


def get_project_member(
    project_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectContext:
    project = project_service.get_project(db, project_id)
    membership = org_service.get_membership(db, project.organization_id, user.id)
    if membership is None:
        raise NotFound("project not found")
    org = org_service.get_organization(db, project.organization_id)
    return ProjectContext(user=user, organization=org, membership=membership, project=project)


def require_project(min_role: Role):
    def _gate(ctx: ProjectContext = Depends(get_project_member)) -> ProjectContext:
        if not ctx.role.at_least(min_role):
            raise Forbidden(f"requires role {min_role.value} or higher")
        return ctx

    return _gate


@dataclass
class ProjectActor:
    """Who is acting on a project: a member (JWT, with a role) or the project's ingest key."""

    project: Project
    organization: Organization
    user: User | None  # None when an ingest key is the caller
    role: Role | None  # None for an ingest key


def get_project_actor(
    project_id: uuid.UUID = Path(...),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> ProjectActor:
    """Data-plane routes (datasets, runs): a member of the org, or this project's `es_…` key."""
    if credentials is not None and credentials.credentials.startswith(INGEST_KEY_PREFIX):
        project, org = get_ingest_project(credentials, db)  # the one ingest-key auth rule
        if project.id != project_id:
            raise NotFound("project not found")  # a valid key for another project: outsider
        return ProjectActor(project=project, organization=org, user=None, role=None)
    ctx = get_project_member(project_id, get_current_user(credentials, db), db)
    return ProjectActor(
        project=ctx.project, organization=ctx.organization, user=ctx.user, role=ctx.role
    )


def get_ingest_project(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> tuple[Project, Organization]:
    """SDK / CI / Turnstile callers present `Authorization: Bearer es_…`."""
    if credentials is None or not credentials.credentials.startswith(INGEST_KEY_PREFIX):
        raise Unauthorized("missing ingest key")
    resolved = project_service.resolve_ingest_key(db, credentials.credentials)
    if resolved is None:
        raise Unauthorized("unknown or revoked ingest key")
    return resolved
