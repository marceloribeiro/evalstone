import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ProjectActor, ProjectContext, get_project_actor, require_project
from app.errors import NotFound
from app.models import Role
from app.schemas.labels import (
    CacheEntryOut,
    CacheLookupIn,
    CachePutIn,
    LabelOut,
    LabelPage,
    LabelsPushIn,
)
from app.services import judge_cache as cache_svc
from app.services import labels as label_svc

router = APIRouter(tags=["judge cache & labels"])

_cache = "/projects/{project_id}/judge-cache"
_labels = "/projects/{project_id}/labels"


@router.post(_cache + "/lookup")
def cache_lookup(
    body: CacheLookupIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """`{key: score}` for the keys the center knows (a suite warms its cache before judging)."""
    return cache_svc.lookup(db, actor.project, body.keys)


@router.get(_cache + "/{key}", response_model=CacheEntryOut)
def cache_get(
    key: str,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    row = cache_svc.get(db, actor.project, key)
    if row is None:
        raise NotFound("no cached verdict for this key")
    return row


@router.put(_cache + "/{key}", response_model=CacheEntryOut)
def cache_put(
    key: str,
    body: CachePutIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """Store a judge verdict under the library's key: 201 when new, 200 when replaced."""
    row, created = cache_svc.put(
        db, actor.project, key, body.score, judge_version=body.judge_version
    )
    payload = CacheEntryOut.model_validate(row).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=payload)


@router.get(_labels, response_model=LabelPage)
def list_labels(
    sample_key: str | None = Query(None),
    check: str | None = Query(None, description="'' for overall labels"),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    rows, total = label_svc.list_labels(
        db, actor.project, sample_key=sample_key, check=check, offset=offset, limit=limit
    )
    return LabelPage(
        items=[LabelOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.post(_labels)
def push_labels(
    body: LabelsPushIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """Upsert labels (a labels.jsonl); later wins per (sample, output, check)."""
    ids = label_svc.upsert(db, project=actor.project, labels=body.labels, labeler_user=actor.user)
    return {"upserted": len(ids)}


@router.get(_labels + "/export")
def export_labels(actor: ProjectActor = Depends(get_project_actor), db: Session = Depends(get_db)):
    """Every live label as NDJSON, streamed — a drop-in `labels.jsonl` for the `human` check."""
    return StreamingResponse(
        label_svc.iter_export(db, actor.project),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="labels.jsonl"'},
    )


@router.get(_labels + "/lookup", response_model=LabelOut)
def lookup_label(
    sample_key: str = Query(..., min_length=1),
    output_hash: str = Query(..., min_length=1, max_length=16),
    check: str | None = Query(None),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """The label for one (sample, output[, check]) — what the `human` check asks at run time."""
    row = label_svc.lookup(
        db, actor.project, sample_key=sample_key, output_hash=output_hash, check=check
    )
    if row is None:
        raise NotFound("no label for this sample/output")
    return row


@router.delete(_labels + "/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    label_svc.soft_delete(db, ctx.project, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
