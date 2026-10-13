import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    ProjectActor,
    ProjectContext,
    get_project_actor,
    get_project_member,
    require_project,
)
from app.models import Role
from app.schemas.monitoring import (
    AlertOut,
    FlagIn,
    MonitorIn,
    MonitorOut,
    MonitorUpdate,
    TraceOut,
    TracePage,
    TracesPushIn,
    WindowOut,
)
from app.services import monitoring as svc

router = APIRouter(tags=["monitoring"])

_p = "/projects/{project_id}"


@router.post(_p + "/traces")
def push_traces(
    body: TracesPushIn,
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    """Production traffic in (the project's `es_…` key or a member); retries dedupe on `id`."""
    records = [t.model_dump(exclude_none=True) for t in body.traces]
    return {"stored": svc.ingest_traces(db, actor.project, records)}


@router.get(_p + "/traces", response_model=TracePage)
def list_traces(
    since: datetime | None = Query(None),
    flagged: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    actor: ProjectActor = Depends(get_project_actor),
    db: Session = Depends(get_db),
):
    rows, total = svc.list_traces(
        db, actor.project, since=since, flagged=flagged, offset=offset, limit=limit
    )
    return TracePage(
        items=[TraceOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.post(_p + "/traces/{trace_id}/flag", response_model=TraceOut)
def flag_trace(
    trace_id: uuid.UUID,
    body: FlagIn,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    """Mark a trace for harvesting into a dataset (a person's judgement call)."""
    return svc.flag_trace(db, svc.get_trace(db, ctx.project, trace_id), flagged=body.flagged)


@router.get(_p + "/monitors", response_model=list[MonitorOut])
def list_monitors(ctx: ProjectContext = Depends(get_project_member), db: Session = Depends(get_db)):
    return svc.list_monitors(db, ctx.project)


@router.post(_p + "/monitors", response_model=MonitorOut, status_code=status.HTTP_201_CREATED)
def create_monitor(
    body: MonitorIn,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.create_monitor(
        db,
        project=ctx.project,
        name=body.name,
        check_keys=body.check_keys,
        sample_rate=body.sample_rate,
        alert_policy=body.alert_policy.model_dump(),
        webhook_url=body.webhook_url,
        created_by=ctx.user,
    )


@router.get(_p + "/monitors/{monitor_id}", response_model=MonitorOut)
def get_monitor(
    monitor_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    return svc.get_monitor(db, ctx.project, monitor_id)


@router.patch(_p + "/monitors/{monitor_id}", response_model=MonitorOut)
def update_monitor(
    monitor_id: uuid.UUID,
    body: MonitorUpdate,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    fields = body.model_dump(exclude_unset=True)
    if "alert_policy" in fields and fields["alert_policy"] is not None:
        fields["alert_policy"] = body.alert_policy.model_dump()
    return svc.update_monitor(
        db, ctx.project, svc.get_monitor(db, ctx.project, monitor_id), **fields
    )


@router.delete(_p + "/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(
    monitor_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    svc.soft_delete_monitor(db, svc.get_monitor(db, ctx.project, monitor_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(_p + "/monitors/{monitor_id}/window", response_model=WindowOut)
def monitor_window(
    monitor_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    """The metrics over the policy's window right now (what the alert policy sees)."""
    return svc.window_metrics(db, svc.get_monitor(db, ctx.project, monitor_id))


@router.post(_p + "/monitors/{monitor_id}/score")
def score_now(
    monitor_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Enqueue one scoring pass now (the beat does this every minute for active monitors)."""
    from app.tasks import score_monitor

    m = svc.get_monitor(db, ctx.project, monitor_id)
    score_monitor.delay(str(m.id))
    return {"enqueued": str(m.id)}


@router.get(_p + "/alerts", response_model=list[AlertOut])
def list_alerts(
    open: bool = Query(False, description="only unresolved alerts"),
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    return svc.list_alerts(db, ctx.project, open_only=open)
