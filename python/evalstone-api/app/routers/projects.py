import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    MemberContext,
    ProjectContext,
    get_ingest_project,
    get_member,
    get_project_member,
    require,
    require_project,
)
from app.models import Project, Role
from app.schemas.projects import (
    IngestKeyCreated,
    IngestKeyIn,
    IngestKeyOut,
    ProjectIn,
    ProjectOut,
    ProjectUpdate,
)
from app.services import projects as svc

router = APIRouter(tags=["projects"])


@router.get("/organizations/{organization_id}/projects", response_model=list[ProjectOut])
def list_projects(ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)):
    return svc.list_projects(db, ctx.organization)


@router.post(
    "/organizations/{organization_id}/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    body: ProjectIn,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.create(db, org=ctx.organization, **body.model_dump())


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(ctx: ProjectContext = Depends(get_project_member)):
    return ctx.project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    body: ProjectUpdate,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.update(db, ctx.project, **body.model_dump(exclude_unset=True))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)), db: Session = Depends(get_db)
):
    svc.soft_delete(db, ctx.project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- ingest keys -------------------------------------------------------------


@router.get("/projects/{project_id}/ingest-keys", response_model=list[IngestKeyOut])
def list_ingest_keys(
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)), db: Session = Depends(get_db)
):
    return svc.list_ingest_keys(db, ctx.project)


@router.post(
    "/projects/{project_id}/ingest-keys",
    response_model=IngestKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_ingest_key(
    body: IngestKeyIn,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    key, secret = svc.create_ingest_key(
        db, project=ctx.project, created_by=ctx.user, name=body.name
    )
    return IngestKeyCreated(**IngestKeyOut.model_validate(key).model_dump(), key=secret)


@router.delete("/projects/{project_id}/ingest-keys/{key_id}", response_model=IngestKeyOut)
def revoke_ingest_key(
    key_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.revoke_ingest_key(db, ctx.project, key_id)


@router.get("/ingest/whoami", response_model=ProjectOut, tags=["ingest"])
def ingest_whoami(project: Project = Depends(get_ingest_project)):
    """What an SDK / CI caller resolves to with its `es_…` key (later slices push runs here)."""
    return project
