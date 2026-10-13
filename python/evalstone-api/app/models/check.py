import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class CheckDefinition(TimestampedModel):
    """An organization's named check: a library check type + its parameters, versioned.

    `key` is what suites reference (`checks: [helpful]`); the current `type` + `params`
    are copied into an immutable `CheckVersion` every time they change, so a run can say
    exactly which rubric/threshold it was graded with.
    """

    __tablename__ = "check_definitions"
    __table_args__ = (
        Index(
            "uq_check_org_key_live",
            "organization_id",
            "key",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)  # a library factory name
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # the library's CheckKind
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class CheckVersion(TimestampedModel):
    """Immutable snapshot of a definition's type + params (content-hashed like the library)."""

    __tablename__ = "check_versions"
    __table_args__ = (
        UniqueConstraint("check_definition_id", "version", name="uq_check_version_number"),
    )

    check_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("check_definitions.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
