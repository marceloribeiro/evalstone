import getpass
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

INSECURE_DOCS_PASSWORDS = {"", "change-me"}


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

    docs_username: str = "evalstone"
    docs_password: str = "change-me"

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
    def _docs_password_is_not_the_published_default(self) -> "Settings":
        """Fail closed: outside development/test the published default must not guard /docs."""
        local = self.app_env in {"development", "test"}
        if not local and self.docs_password in INSECURE_DOCS_PASSWORDS:
            what = "empty" if not self.docs_password else "the published default"
            raise ValueError(f"DOCS_PASSWORD is {what}; set a real one in .env ({self.app_env})")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
