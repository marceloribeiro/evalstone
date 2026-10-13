import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ProjectContext, get_project_member, require_project
from app.models import Role
from app.schemas.calibration import CalibrationIn, CalibrationOut, JudgeOut
from app.services import calibration as svc

router = APIRouter(tags=["calibration"])

_p = "/projects/{project_id}"


@router.get(_p + "/judges", response_model=list[JudgeOut])
def list_judges(ctx: ProjectContext = Depends(get_project_member), db: Session = Depends(get_db)):
    """Every judge version seen in this project's runs (check, version hash, model, counts)."""
    return svc.judges(db, ctx.project)


@router.post(_p + "/calibrations", response_model=CalibrationOut, status_code=202)
def request_calibration(
    body: CalibrationIn,
    ctx: ProjectContext = Depends(require_project(Role.MEMBER)),
    db: Session = Depends(get_db),
):
    """Queue a calibration job; poll the row until `status` is done or failed."""
    return svc.request(db, project=ctx.project, created_by=ctx.user, **body.model_dump())


@router.get(_p + "/calibrations", response_model=list[CalibrationOut])
def list_calibrations(
    check_key: str | None = Query(None),
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    return svc.list_calibrations(db, ctx.project, check_key=check_key)


@router.get(_p + "/calibrations/{calibration_id}", response_model=CalibrationOut)
def get_calibration(
    calibration_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_member),
    db: Session = Depends(get_db),
):
    return svc.get_calibration(db, ctx.project, calibration_id)
