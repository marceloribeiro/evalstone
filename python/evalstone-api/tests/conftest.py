import os

os.environ["APP_ENV"] = "test"  # the engine picks DB_TEST_NAME; never the development DB
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-32")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # fast hashes; production keeps 12

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Base


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


@pytest.fixture
def register(client):
    """register("a@x.com") → (auth headers, user json)."""

    def _register(email: str, password: str = "password123", **names):
        r = client.post("/auth/register", json={"email": email, "password": password, **names})
        assert r.status_code == 201, r.text
        body = r.json()
        return {"Authorization": f"Bearer {body['token']}"}, body["user"]

    return _register


@pytest.fixture
def org(client, register):
    """An owner and their organization: {"headers", "user", "id"}."""
    headers, user = register("owner@acme.example.com")
    o = client.post("/organizations", json={"name": "Acme"}, headers=headers)
    assert o.status_code == 201, o.text
    return {"headers": headers, "user": user, "id": o.json()["id"]}


@pytest.fixture
def project(client, org):
    """A project inside `org`: {"id", "headers", "org"}."""
    p = client.post(
        f"/organizations/{org['id']}/projects", json={"name": "RAG Bot"}, headers=org["headers"]
    )
    assert p.status_code == 201, p.text
    return {"id": p.json()["id"], "headers": org["headers"], "org": org}
