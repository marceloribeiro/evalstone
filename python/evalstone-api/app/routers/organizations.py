import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MemberContext, get_current_user, get_member, require
from app.models import Role, User
from app.schemas.organizations import (
    InvitationIn,
    InvitationOut,
    MemberOut,
    MemberUpdate,
    OrganizationIn,
    OrganizationOut,
    OrganizationUpdate,
)
from app.services import organizations as svc

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationOut])
def list_organizations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.list_for_user(db, user)


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    body: OrganizationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.create(db, owner=user, **body.model_dump())


@router.get("/{organization_id}", response_model=OrganizationOut)
def get_organization(ctx: MemberContext = Depends(get_member)):
    return ctx.organization


@router.patch("/{organization_id}", response_model=OrganizationOut)
def update_organization(
    body: OrganizationUpdate,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return svc.update(db, ctx.organization, **body.model_dump(exclude_unset=True))


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    ctx: MemberContext = Depends(require(Role.OWNER)), db: Session = Depends(get_db)
):
    svc.soft_delete(db, ctx.organization)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- members -----------------------------------------------------------------


@router.get("/{organization_id}/members", response_model=list[MemberOut])
def list_members(ctx: MemberContext = Depends(get_member), db: Session = Depends(get_db)):
    return svc.list_members(db, ctx.organization)


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberOut)
def set_member_role(
    member_id: uuid.UUID,
    body: MemberUpdate,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    member = svc.get_member(db, ctx.organization, member_id)
    return svc.set_role(db, actor_role=ctx.role, member=member, role=body.role)


@router.delete("/{organization_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: uuid.UUID,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    member = svc.get_member(db, ctx.organization, member_id)
    svc.remove_member(db, actor_role=ctx.role, member=member)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- invitations -------------------------------------------------------------


@router.get("/{organization_id}/invitations", response_model=list[InvitationOut])
def list_invitations(
    ctx: MemberContext = Depends(require(Role.ADMIN)), db: Session = Depends(get_db)
):
    return [InvitationOut.of(i) for i in svc.list_invitations(db, ctx.organization)]


@router.post(
    "/{organization_id}/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
)
def invite(
    body: InvitationIn,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    inv = svc.invite(db, org=ctx.organization, invited_by=ctx.user, **body.model_dump())
    return InvitationOut.of(inv)


@router.delete(
    "/{organization_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_invitation(
    invitation_id: uuid.UUID,
    ctx: MemberContext = Depends(require(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    svc.revoke_invitation(db, ctx.organization, invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
