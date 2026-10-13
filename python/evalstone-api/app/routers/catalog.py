import uuid

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MemberContext, get_current_user, get_member, require
from app.models import Role, User
from app.schemas.catalog import BuiltinOut, CheckIn, CheckOut, CheckUpdate, CheckVersionOut
from app.services import catalog as svc

router = APIRouter(tags=["check catalog"])

_org = "/organizations/{organization_id}/checks"


@router.get("/catalog/checks", response_model=list[BuiltinOut])
def builtin_checks(_: User = Depends(get_current_user)):
    """The library's built-in check types (the version this center runs), with their params."""
    return svc.builtins()


@router.get(_org, response_model=list[CheckOut])
def list_checks(ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)):
    return svc.list_checks(db, ctx.organization)


@router.get(_org + "/yaml")
def checks_as_yaml(ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)):
    """The org's checks as the `checks:` block of an evalstone.yaml (paste or pull)."""
    return JSONResponse(content={"checks": svc.as_yaml_spec(svc.list_checks(db, ctx.organization))})


@router.post(_org, response_model=CheckOut, status_code=status.HTTP_201_CREATED)
def create_check(
    body: CheckIn,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.create(
        db,
        org=ctx.organization,
        key=body.key,
        check_type=body.type,
        params=body.params,
        description=body.description,
        created_by=ctx.user,
    )


@router.get(_org + "/{check_id}", response_model=CheckOut)
def get_check(
    check_id: uuid.UUID, ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)
):
    return svc.get_check(db, ctx.organization, check_id)


@router.put(_org + "/{check_id}", response_model=CheckOut)
def update_check(
    check_id: uuid.UUID,
    body: CheckUpdate,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Edit: a type/params change creates the next version (201); description only → 200."""
    row = svc.get_check(db, ctx.organization, check_id)
    row, changed = svc.update(
        db,
        row,
        check_type=body.type,
        params=body.params,
        description=body.description,
        note=body.note,
        by=ctx.user,
    )
    payload = CheckOut.model_validate(row).model_dump(mode="json")
    return JSONResponse(status_code=201 if changed else 200, content=payload)


@router.delete(_org + "/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check(
    check_id: uuid.UUID,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    svc.soft_delete(db, svc.get_check(db, ctx.organization, check_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(_org + "/{check_id}/versions", response_model=list[CheckVersionOut])
def list_versions(
    check_id: uuid.UUID, ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)
):
    return svc.list_versions(db, svc.get_check(db, ctx.organization, check_id))


@router.get(_org + "/{check_id}/versions/{version}", response_model=CheckVersionOut)
def get_version(
    check_id: uuid.UUID,
    version: int,
    ctx: MemberContext = Depends(get_member),
    db: Session = Depends(get_db),
):
    return svc.get_version(db, svc.get_check(db, ctx.organization, check_id), version)
