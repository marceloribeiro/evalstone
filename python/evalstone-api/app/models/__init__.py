"""Every model module is imported here so Alembic autogenerate and the console see all tables."""

from app.models.base import Base, TimestampedModel
from app.models.organization import Organization, OrganizationInvitation, OrganizationMember, Role
from app.models.project import IngestKey, Project
from app.models.provider import ADAPTERS, JudgeSettings, Provider
from app.models.user import User

__all__ = [
    "ADAPTERS",
    "Base",
    "IngestKey",
    "JudgeSettings",
    "Organization",
    "OrganizationInvitation",
    "OrganizationMember",
    "Project",
    "Provider",
    "Role",
    "TimestampedModel",
    "User",
]
