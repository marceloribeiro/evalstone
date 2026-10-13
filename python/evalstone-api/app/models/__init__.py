"""Every model module is imported here so Alembic autogenerate and the console see all tables."""

from app.models.base import Base, TimestampedModel

__all__ = ["Base", "TimestampedModel"]
