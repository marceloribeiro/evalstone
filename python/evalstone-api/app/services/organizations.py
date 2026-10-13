"""Organizations, members and invitations. Routers never touch the session; these functions do."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import Conflict, Invalid, NotFound
from app.models import Organization, OrganizationInvitation, OrganizationMember, Role, User
from app.services.users import get_user_by_email, normalize_email


def list_for_user(db: Session, user: User) -> list[Organization]:
    return list(
        db.scalars(
            select(Organization)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.deleted_at.is_(None),
                Organization.deleted_at.is_(None),
            )
            .order_by(Organization.created_at)
        ).all()
    )


def get_organization(db: Session, org_id: uuid.UUID) -> Organization:
    org = db.get(Organization, org_id)
    if org is None or org.deleted_at is not None:
        raise NotFound("organization not found")
    return org


def create(db: Session, *, owner: User, name: str, website_url: str | None = None) -> Organization:
    """ORGANIZATION_BASED rule: the creator becomes the owner."""
    org = Organization(name=name, website_url=website_url)
    db.add(org)
    db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=owner.id, role=Role.OWNER))
    db.commit()
    db.refresh(org)
    return org


def update(db: Session, org: Organization, **fields) -> Organization:
    for k, v in fields.items():
        setattr(org, k, v)
    db.commit()
    db.refresh(org)
    return org


def soft_delete(db: Session, org: Organization) -> None:
    org.deleted_at = datetime.now(UTC)
    db.commit()


# --- members -----------------------------------------------------------------


def get_membership(db: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> OrganizationMember | None:
    return db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.deleted_at.is_(None),
        )
    )


def list_members(db: Session, org: Organization) -> list[OrganizationMember]:
    return list(
        db.scalars(
            select(OrganizationMember)
            .where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.deleted_at.is_(None),
            )
            .order_by(OrganizationMember.created_at)
        ).all()
    )


def get_member(db: Session, org: Organization, member_id: uuid.UUID) -> OrganizationMember:
    m = db.get(OrganizationMember, member_id)
    if m is None or m.deleted_at is not None or m.organization_id != org.id:
        raise NotFound("member not found")
    return m


def _owner_count(db: Session, org_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.role == Role.OWNER,
            OrganizationMember.deleted_at.is_(None),
        )
    )


def _guard_last_owner(db: Session, member: OrganizationMember) -> None:
    if member.role == Role.OWNER and _owner_count(db, member.organization_id) <= 1:
        raise Invalid("an organization keeps at least one owner")


def set_role(
    db: Session, *, actor_role: Role, member: OrganizationMember, role: Role
) -> OrganizationMember:
    """Admins manage members; only owners grant or take away ownership."""
    if (role == Role.OWNER or member.role == Role.OWNER) and actor_role != Role.OWNER:
        raise Invalid("only an owner can change ownership")
    if role != Role.OWNER:
        _guard_last_owner(db, member)
    member.role = role
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, *, actor_role: Role, member: OrganizationMember) -> None:
    if member.role == Role.OWNER and actor_role != Role.OWNER:
        raise Invalid("only an owner can remove an owner")
    _guard_last_owner(db, member)
    member.deleted_at = datetime.now(UTC)
    db.commit()


# --- invitations -------------------------------------------------------------


def list_invitations(db: Session, org: Organization) -> list[OrganizationInvitation]:
    return list(
        db.scalars(
            select(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == org.id,
                OrganizationInvitation.deleted_at.is_(None),
            )
            .order_by(OrganizationInvitation.created_at)
        ).all()
    )


def invite(
    db: Session, *, org: Organization, invited_by: User, email: str, role: Role = Role.MEMBER
) -> OrganizationInvitation:
    """Pending until the address registers; an existing user is added on the spot."""
    email = normalize_email(email)
    if role == Role.OWNER:
        raise Invalid("ownership is granted to members, not by invitation")
    existing = get_user_by_email(db, email)
    if existing is not None and get_membership(db, org.id, existing.id) is not None:
        raise Conflict("already a member")
    open_invite = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == org.id,
            func.lower(OrganizationInvitation.email) == email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.deleted_at.is_(None),
        )
    )
    if open_invite is not None:
        raise Conflict("already invited")
    inv = OrganizationInvitation(
        organization_id=org.id, email=email, role=role, invited_by_user_id=invited_by.id
    )
    db.add(inv)
    if existing is not None:
        db.add(OrganizationMember(organization_id=org.id, user_id=existing.id, role=role))
        inv.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(inv)
    return inv


def revoke_invitation(db: Session, org: Organization, invitation_id: uuid.UUID) -> None:
    inv = db.get(OrganizationInvitation, invitation_id)
    if inv is None or inv.deleted_at is not None or inv.organization_id != org.id:
        raise NotFound("invitation not found")
    if inv.accepted_at is not None:
        raise Invalid("invitation already accepted")
    inv.deleted_at = datetime.now(UTC)
    db.commit()
