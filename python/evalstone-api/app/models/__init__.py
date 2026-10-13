"""Every model module is imported here so Alembic autogenerate and the console see all tables."""

from app.models.base import Base, TimestampedModel
from app.models.dataset import Dataset, DatasetVersion, DatasetVersionSample, Sample
from app.models.organization import Organization, OrganizationInvitation, OrganizationMember, Role
from app.models.project import IngestKey, Project
from app.models.provider import ADAPTERS, JudgeSettings, Provider
from app.models.user import User

__all__ = [
    "ADAPTERS",
    "Base",
    "Dataset",
    "DatasetVersion",
    "DatasetVersionSample",
    "IngestKey",
    "JudgeSettings",
    "Organization",
    "OrganizationInvitation",
    "OrganizationMember",
    "Project",
    "Provider",
    "Role",
    "Sample",
    "TimestampedModel",
    "User",
]
