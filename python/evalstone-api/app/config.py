import getpass
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

INSECURE_SECRETS = {"", "change-me", "dev-only-change-me-dev-only-change-me"}
MIN_JWT_SECRET_BYTES = 32  # HS256 key floor (RFC 7518 §3.2)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "evalstone-api"
    app_env: str = "development"
    app_port: int = 8181

    db_user: str = getpass.getuser()  # native Postgres: the OS user owns the cluster
    db_pass: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "evalstone_api_development"
    db_test_name: str = "evalstone_api_test"

    redis_url: str = "redis://localhost:6379/7"
    celery_broker_url: str = "redis://localhost:6379/7"
    celery_result_backend: str = "redis://localhost:6379/7"
    celery_task_always_eager: bool = False  # tests: run tasks in-process
    # Every Celery key (queues, bindings, pidbox, results) is namespaced with this prefix, so one
    # Redis index can be shared with another app's Celery without consuming each other's tasks
    # (the live box has a Celery app on every index). Pub/sub channels already carry it.
    redis_key_prefix: str = "evalstone:"

    docs_username: str = "evalstone"
    docs_password: str = "change-me"

    jwt_secret: str  # no default: set JWT_SECRET (see .env.example); ≥ 32 bytes outside dev/test
    jwt_expires_minutes: int = 60 * 24 * 7
    bcrypt_rounds: int = 12  # tests lower it; production keeps the default

    # Fernet key for org provider API keys; empty derives a fixed key in development/test only
    provider_creds_key: str = ""
    provider_allow_private_urls: bool = False  # self-hosted Ollama next to the center
    provider_test_timeout_s: float = 15.0

    cors_origins: str = "http://localhost:3000"  # comma-separated

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def active_db_name(self) -> str:
        """The database this process talks to: the `_test` twin under APP_ENV=test."""
        return self.db_test_name if self.is_test else self.db_name

    def database_url(self, name: str | None = None) -> str:
        """A URL whose user/password are percent-encoded, so secrets with @ : / # % still parse."""
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_pass or None,
            host=self.db_host,
            port=self.db_port,
            database=name or self.active_db_name,
        ).render_as_string(hide_password=False)

    @model_validator(mode="after")
    def _secrets_are_not_the_published_defaults(self) -> "Settings":
        """Fail closed: outside development/test a published dev value must not guard anything."""
        if self.app_env in {"development", "test"}:
            return self
        for name, value in (("DOCS_PASSWORD", self.docs_password), ("JWT_SECRET", self.jwt_secret)):
            if value in INSECURE_SECRETS:
                what = "empty" if not value else "the published default"
                raise ValueError(f"{name} is {what}; set a real one in .env ({self.app_env})")
        if len(self.jwt_secret.encode()) < MIN_JWT_SECRET_BYTES:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_BYTES} bytes (RFC 7518)")
        if not self.provider_creds_key:
            raise ValueError("PROVIDER_CREDS_KEY is empty; set a Fernet key and never change it")
        try:
            Fernet(self.provider_creds_key.encode())
        except (ValueError, TypeError) as err:
            raise ValueError(
                "PROVIDER_CREDS_KEY is not a valid Fernet key (python -c "
                "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
            ) from err
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
