from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "evalstone-api"
    app_env: str = "development"
    app_port: int = 8181

    db_user: str = "marcelo"
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
        db = name or self.active_db_name
        auth = self.db_user if not self.db_pass else f"{self.db_user}:{self.db_pass}"
        return f"postgresql+psycopg://{auth}@{self.db_host}:{self.db_port}/{db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
