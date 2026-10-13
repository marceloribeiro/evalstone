import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ProjectActor, ProjectContext, get_project_actor, require_project
from app.models import Role
from app.schemas.datasets import (
    DatasetIn,
    DatasetOut,
    DatasetUpdate,
    SampleOut,
    SamplePage,
    VersionIn,
    VersionOut,
)
from app.services import datasets as svc

router = APIRouter(tags=["datasets"])

_p = "/projects/{project_id}/datasets"


@router.get(_p, response_model=list[DatasetOut])
def list_datasets(actor: ProjectActor = Depends(get_project_actor), db: Session = Depends(get_db)):
    return svc.list_datasets(db, actor.project)


@router.post(_p, response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def create_dataset(
    body: DatasetIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    return svc.create(db, project=actor.project, **body.model_dump())


@router.get(_p + "/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: uuid.UUID,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    return svc.get_dataset(db, actor.project, dataset_id)


@router.patch(_p + "/{dataset_id}", response_model=DatasetOut)
def update_dataset(
    dataset_id: uuid.UUID,
    body: DatasetUpdate,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    d = svc.get_dataset(db, ctx.project, dataset_id)
    return svc.update(db, d, **body.model_dump(exclude_unset=True))


@router.delete(_p + "/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    svc.soft_delete(db, svc.get_dataset(db, ctx.project, dataset_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- versions -----------------------------------------------------------------------------


@router.get(_p + "/{dataset_id}/versions", response_model=list[VersionOut])
def list_versions(
    dataset_id: uuid.UUID,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    return svc.list_versions(db, svc.get_dataset(db, actor.project, dataset_id))


@router.post(_p + "/{dataset_id}/versions", response_model=VersionOut)
def create_version(
    dataset_id: uuid.UUID,
    body: VersionIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """Snapshot the samples as the next version: 201 when new, 200 + latest when unchanged."""
    d = svc.get_dataset(db, actor.project, dataset_id)
    version, created = svc.create_version(
        db,
        dataset=d,
        records=[s.model_dump() for s in body.samples],
        note=body.note,
        created_by=actor.user,
    )
    payload = VersionOut.model_validate(version).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=payload)


@router.get(_p + "/{dataset_id}/versions/{version}", response_model=VersionOut)
def get_version(
    dataset_id: uuid.UUID,
    version: int,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    return svc.get_version(db, svc.get_dataset(db, actor.project, dataset_id), version)


@router.get(_p + "/{dataset_id}/versions/{version}/samples", response_model=SamplePage)
def version_samples(
    dataset_id: uuid.UUID,
    version: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    v = svc.get_version(db, svc.get_dataset(db, actor.project, dataset_id), version)
    rows, total = svc.version_samples(db, v, offset=offset, limit=limit)
    return SamplePage(
        items=[SampleOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )
