from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ProjectActor, get_project_actor
from app.schemas.model_proxy import CompleteIn, CompleteOut, ModelCallOut, ModelCallPage, UsageOut
from app.services import model_proxy as svc

router = APIRouter(tags=["model proxy"])


@router.post("/projects/{project_id}/model/complete", response_model=CompleteOut)
def complete(
    body: CompleteIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """One model call with the org's key, server-side; the response is the library's shape.

    502 when the provider fails (the call is still metered as failed); 422 when no model
    can be resolved.
    """
    resp = svc.complete(
        db,
        project=actor.project,
        caller=actor.user,
        model=body.model,
        check_key=body.check_key,
        system=body.system,
        messages=body.messages,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )
    return CompleteOut(**resp.model_dump(exclude={"raw"}))


@router.get("/projects/{project_id}/model/calls", response_model=ModelCallPage)
def list_calls(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    rows, total = svc.list_calls(db, actor.project, offset=offset, limit=limit)
    return ModelCallPage(
        items=[ModelCallOut.model_validate(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/projects/{project_id}/model/usage", response_model=UsageOut)
def get_usage(actor: ProjectActor = Depends(get_project_actor), db: Session = Depends(get_db)):
    """Totals over every metered call (one aggregate, separate from paging the history)."""
    return svc.usage(db, actor.project)
