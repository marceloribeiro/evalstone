import os

os.environ["APP_ENV"] = "test"  # the engine picks DB_TEST_NAME; never the development DB
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")

import pytest
from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy import text


@pytest.fixture(scope="session", autouse=True)
def migrated_test_db():
    """Bring the `_test` database to head once per session (tests hit the real native Postgres)."""
    os.environ["ALEMBIC_DB_NAME"] = get_settings().db_test_name
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    tables = [f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)]
    if tables:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
