"""Users: register (auto-accepts pending invitations), login, lookup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import Conflict, Unauthorized
from app.models import OrganizationInvitation, OrganizationMember, User
from app.security import hash_password, verify_password


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).where(
            func.lower(User.email) == normalize_email(email), User.deleted_at.is_(None)
        )
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
            func.lower(OrganizationInvitation.email) == user.email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.deleted_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for inv in pending:
        db.add(
            OrganizationMember(organization_id=inv.organization_id, user_id=user.id, role=inv.role)
        )
        inv.accepted_at = now
    return len(pending)


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise Unauthorized("invalid email or password")
    return user
