import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ProjectContext, get_project_member, require_project
from app.errors import NotFound
from app.models import Role
from app.schemas.label_queues import (
    AnswerIn,
    AssignIn,
    ProgressOut,
    QueueIn,
    QueueOut,
    QueueStatusIn,
    SkipIn,
    TaskOut,
    TaskPage,
)
from app.services import label_queues as svc

router = APIRouter(tags=["labeling"])

_q = "/projects/{project_id}/label-queues"


@router.get(_q, response_model=list[QueueOut])
def list_queues(ctx: ProjectContext = Depends(get_project_member), db: Session = Depends(get_db)):
    return svc.list_queues(db, ctx.project)


@router.post(_q, response_model=QueueOut, status_code=201)
def create_queue(
    body: QueueIn,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Materialise the tasks now: one per sample of the source run(s) or dataset version."""
    return svc.create(db, project=ctx.project, created_by=ctx.user, **body.model_dump())


@router.get(_q + "/{queue_id}", response_model=QueueOut)
def get_queue(
    queue_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    return svc.get_queue(db, ctx.project, queue_id)


@router.patch(_q + "/{queue_id}", response_model=QueueOut)
def set_queue_status(
    queue_id: uuid.UUID,
    body: QueueStatusIn,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.close(db, svc.get_queue(db, ctx.project, queue_id), status=body.status)


@router.get(_q + "/{queue_id}/progress", response_model=ProgressOut)
def queue_progress(
    queue_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    return svc.progress(db, svc.get_queue(db, ctx.project, queue_id))


@router.post(_q + "/{queue_id}/assign")
def assign_tasks(
    queue_id: uuid.UUID,
    body: AssignIn,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Round-robin the unassigned pending tasks over the given members."""
    n = svc.assign(db, svc.get_queue(db, ctx.project, queue_id), body.user_ids)
    return {"assigned": n}


@router.get(_q + "/{queue_id}/tasks", response_model=TaskPage)
def list_tasks(
    queue_id: uuid.UUID,
    status: str | None = Query(None, pattern="^(pending|done|skipped)$"),
    assignee: str | None = Query(None, description="'me' or a user id"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    queue = svc.get_queue(db, ctx.project, queue_id)
    who = None
    if assignee == "me":
        who = ctx.user.id
    elif assignee:
        try:
            who = uuid.UUID(assignee)
        except ValueError as err:
            raise NotFound("assignee not found") from err
    rows, total = svc.list_tasks(
        db, queue, status=status, assignee_user_id=who, offset=offset, limit=limit
    )
    return TaskPage(
        items=[TaskOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.post(_q + "/{queue_id}/next", response_model=TaskOut | None)
def next_task(
    queue_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    """Claim the next task for me (mine first, else an unassigned one); null when none is left."""
    return svc.claim_next(db, svc.get_queue(db, ctx.project, queue_id), ctx.user)


@router.post(_q + "/{queue_id}/tasks/{task_id}/answer", response_model=TaskOut)
def answer_task(
    queue_id: uuid.UUID,
    task_id: uuid.UUID,
    body: AnswerIn,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    """Record the verdict: it becomes a label (sample + output hash) and the task is done."""
    queue = svc.get_queue(db, ctx.project, queue_id)
    task = svc.get_task(db, ctx.project, task_id)
    return svc.complete(
        db,
        queue=queue,
        task=task,
        user=ctx.user,
        grade=body.grade,
        passed=body.passed,
        notes=body.notes,
        winner=body.winner,
    )


@router.post(_q + "/{queue_id}/tasks/{task_id}/skip", response_model=TaskOut)
def skip_task(
    queue_id: uuid.UUID,
    task_id: uuid.UUID,
    body: SkipIn,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    svc.get_queue(db, ctx.project, queue_id)
    return svc.skip(db, svc.get_task(db, ctx.project, task_id), ctx.user, reason=body.reason)
