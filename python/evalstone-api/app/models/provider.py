import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel

ADAPTERS = ("openai", "anthropic", "gemini")  # mirrors evalstone.providers.ADAPTERS


class Provider(TimestampedModel):
    """An org's named model endpoint: `name` + adapter + base_url + encrypted key (+ prices).

    The judge model string is `<name>/<model>`, so `openrouter`, `openai` and a local `ollama`
    entry can coexist in one org, each with its own key.
    """

    __tablename__ = "providers"
    __table_args__ = (
        Index(
            "uq_provider_org_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    adapter: Mapped[str] = mapped_column(String(20), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet token
    key_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prices: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # model → [in, out]
    timeout_s: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    max_tokens_param: Mapped[str | None] = mapped_column(String(30), nullable=True)
    verified_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def has_api_key(self) -> bool:
        return self.encrypted_api_key is not None


class JudgeSettings(TimestampedModel):
    """Per project: the default judge model and per-check overrides, all `<provider>/<model>`."""

    __tablename__ = "judge_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, unique=True
    )
    default_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    overrides: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # check_key → model
