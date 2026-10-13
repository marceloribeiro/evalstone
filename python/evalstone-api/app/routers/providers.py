import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    MemberContext,
    ProjectContext,
    get_member,
    get_project_member,
    require,
    require_project,
)
from app.models import Role
from app.schemas.providers import (
    JudgeSettingsIn,
    JudgeSettingsOut,
    ProviderIn,
    ProviderOut,
    ProviderTestIn,
    ProviderTestOut,
    ProviderUpdate,
)
from app.services import judge_settings as judge_svc
from app.services import providers as svc

router = APIRouter(tags=["providers"])

_org = "/organizations/{organization_id}/providers"


@router.get(_org, response_model=list[ProviderOut])
def list_providers(ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)):
    return svc.list_providers(db, ctx.organization)


@router.post(_org, response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(
    body: ProviderIn,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.create(db, org=ctx.organization, **body.model_dump())


@router.get(_org + "/{provider_id}", response_model=ProviderOut)
def get_provider(
    provider_id: uuid.UUID,
    ctx: MemberContext = Depends(get_member),
    db: Session = Depends(get_db),
):
    return svc.get_provider(db, ctx.organization, provider_id)


@router.patch(_org + "/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    p = svc.get_provider(db, ctx.organization, provider_id)
    return svc.update(db, p, **body.model_dump(exclude_unset=True))


@router.delete(_org + "/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    provider_id: uuid.UUID,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    svc.soft_delete(db, svc.get_provider(db, ctx.organization, provider_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(_org + "/{provider_id}/test", response_model=ProviderTestOut)
def test_provider(
    provider_id: uuid.UUID,
    body: ProviderTestIn,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """One tiny completion with the stored key; reports latency, tokens and cost."""
    p = svc.get_provider(db, ctx.organization, provider_id)
    return svc.test_provider(db, p, model=body.model)


@router.get("/projects/{project_id}/judge-settings", response_model=JudgeSettingsOut)
def get_judge_settings(
    ctx: ProjectContext = Depends(get_project_member), db: Session = Depends(get_db)
):
    return judge_svc.get_or_default(db, ctx.project)


@router.put("/projects/{project_id}/judge-settings", response_model=JudgeSettingsOut)
def put_judge_settings(
    body: JudgeSettingsIn,
    ctx: ProjectContext = Depends(require_project(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return judge_svc.put(db, ctx.project, **body.model_dump())
