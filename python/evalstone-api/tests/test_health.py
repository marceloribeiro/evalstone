from app.config import get_settings
from app.routers import health


def test_health_is_up_without_dependencies(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_reports_database_and_redis(client):
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ready", "database": "ok", "redis": "ok"}


def test_ready_is_503_and_names_the_dependency_when_redis_is_down(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "redis_url", "redis://localhost:1/7")  # nothing listens on port 1
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["detail"] == {"status": "not_ready", "database": "ok", "redis": "down"}


def test_ready_is_503_when_the_database_is_down(client):
    class BrokenSession:
        def execute(self, *_):
            raise RuntimeError("connection refused")

        def close(self):
            pass

    def broken_db():
        yield BrokenSession()

    from app.db import get_db

    client.app.dependency_overrides[get_db] = broken_db
    try:
        r = client.get("/ready")
    finally:
        client.app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["detail"]["database"] == "down"
    assert health.router is not None


def test_docs_require_basic_auth(client):
    s = get_settings()
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/docs", auth=(s.docs_username, "wrong")).status_code == 401
    assert client.get("/docs", auth=(s.docs_username, s.docs_password)).status_code == 200
    spec = client.get("/openapi.json", auth=(s.docs_username, s.docs_password)).json()
    assert "/health" in spec["paths"] and "/ready" in spec["paths"]
