import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ProjectActor, ProjectContext, get_project_actor, require_project
from app.models import Role
from app.schemas.runs import BaselineIn, ResultOut, ResultPage, RunOut, RunPage
from app.services import runs as svc

router = APIRouter(tags=["runs"])

_p = "/projects/{project_id}/runs"


@router.post(_p, response_model=RunOut)
def push_run(
    report: dict[str, Any] = Body(..., description="A library report (evalstone-report.json)"),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """Store a run: 201 when new, 200 with the stored run when this client run id exists."""
    run, created = svc.ingest(db, project=actor.project, report=report, created_by=actor.user)
    payload = RunOut.model_validate(run).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=payload)


@router.get(_p, response_model=RunPage)
def list_runs(
    suite: str | None = Query(None),
    baseline: bool = Query(False, description="only the current baselines"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    rows, total = svc.list_runs(
        db, actor.project, suite=suite, baseline_only=baseline, offset=offset, limit=limit
    )
    return RunPage(
        items=[RunOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.get(_p + "/{run_id}", response_model=RunOut)
def get_run(
    run_id: uuid.UUID,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    return svc.get_run(db, actor.project, run_id)


@router.get(_p + "/{run_id}/results", response_model=ResultPage)
def list_results(
    run_id: uuid.UUID,
    check_key: str | None = Query(None),
    failed_only: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    run = svc.get_run(db, actor.project, run_id)
    rows, total = svc.list_results(
        db, run, check_key=check_key, failed_only=failed_only, offset=offset, limit=limit
    )
    return ResultPage(
        items=[ResultOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.get(_p + "/{run_id}/report")
def get_report(
    run_id: uuid.UUID,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """The run as the library's report JSON (`evalstone compare` / `--baseline` can consume it)."""
    run = svc.get_run(db, actor.project, run_id)
    return JSONResponse(content=svc.to_library_run(db, run).model_dump(mode="json"))


@router.get(_p + "/{run_id}/compare/{other_id}")
def compare(
    run_id: uuid.UUID,
    other_id: uuid.UUID,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """Run B (`other_id`) relative to run A, the library's `compare()` over the stored rows."""
    a = svc.get_run(db, actor.project, run_id)
    b = svc.get_run(db, actor.project, other_id)
    return JSONResponse(content=svc.compare_runs(db, a, b).model_dump(mode="json"))


@router.put(_p + "/{run_id}/baseline", response_model=RunOut)
def set_baseline(
    run_id: uuid.UUID,
    body: BaselineIn,
    ctx: ProjectContext = Depends(require_project(Role.MEMBER)),
    db: Session = Depends(get_db),
):
    """Mark (or unmark) the baseline for this run's suite; one baseline per suite."""
    run = svc.get_run(db, ctx.project, run_id)
    return svc.set_baseline(db, run, value=body.is_baseline)
