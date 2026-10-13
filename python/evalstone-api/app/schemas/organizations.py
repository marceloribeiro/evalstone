import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Role
from app.schemas.auth import UserOut


class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website_url: str | None = Field(default=None, max_length=500)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website_url: str | None = Field(default=None, max_length=500)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    website_url: str | None
    created_at: datetime


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Role
    user: UserOut
    created_at: datetime


class MemberUpdate(BaseModel):
    role: Role


class InvitationIn(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Role
    status: Literal["pending", "accepted"]
    created_at: datetime
    accepted_at: datetime | None

    @classmethod
    def of(cls, inv) -> "InvitationOut":
        return cls(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            status="accepted" if inv.accepted_at else "pending",
            created_at=inv.created_at,
            accepted_at=inv.accepted_at,
        )
