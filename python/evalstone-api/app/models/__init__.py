"""Every model module is imported here so Alembic autogenerate and the console see all tables."""

from app.models.base import Base, TimestampedModel
from app.models.organization import Organization, OrganizationInvitation, OrganizationMember, Role
from app.models.project import IngestKey, Project
from app.models.user import User

__all__ = [
    "Base",
    "IngestKey",
    "Organization",
    "OrganizationInvitation",
    "OrganizationMember",
    "Project",
    "Role",
    "TimestampedModel",
    "User",
]
