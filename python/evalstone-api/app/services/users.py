"""Users: register (auto-accepts pending invitations), login, lookup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, Unauthorized
from app.models import OrganizationInvitation, OrganizationMember, Role, User
from app.security import hash_password, verify_password

# verified against when the email is unknown, so a miss costs the same as a wrong password
_DUMMY_HASH = hash_password("not-a-real-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    # emails are stored normalised, so an equality hits ix_users_email (lower() would not)
    return db.scalar(
        select(User).where(User.email == normalize_email(email), User.deleted_at.is_(None))
    )


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    user = db.get(User, user_id)
    return None if user is None or user.deleted_at is not None else user


def register(
    db: Session, *, email: str, password: str, first_name: str = "", last_name: str = ""
) -> User:
    email = normalize_email(email)
    if get_user_by_email(db, email) is not None:
        raise Conflict("email already registered")
    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
    )
    db.add(user)
    db.flush()
    _accept_pending_invitations(db, user)
    db.commit()
    db.refresh(user)
    return user


def _accept_pending_invitations(db: Session, user: User) -> int:
    """ORGANIZATION_BASED rule: a new user joins every org that invited their email."""
    pending = db.scalars(
        select(OrganizationInvitation).where(
            OrganizationInvitation.email == user.email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.deleted_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for inv in pending:
        add_or_revive_member(
            db, organization_id=inv.organization_id, user_id=user.id, role=inv.role
        )
        inv.accepted_at = now
    return len(pending)


def add_or_revive_member(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, role: Role
) -> OrganizationMember:
    """Membership rows are soft-deleted and (org, user) is unique: a returning user is revived."""
    existing = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if existing is None:
        existing = OrganizationMember(organization_id=organization_id, user_id=user_id, role=role)
        db.add(existing)
    else:
        existing.deleted_at = None
        existing.role = role
    return existing


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)  # no timing oracle for account enumeration
        raise Unauthorized("invalid email or password")
    if not verify_password(password, user.password_hash):
        raise Unauthorized("invalid email or password")
    return user
