from app.config import get_settings
from app.db import get_db
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

        def rollback(self):
            pass

        def close(self):
            pass

    def broken_db():
        yield BrokenSession()

    client.app.dependency_overrides[get_db] = broken_db
    try:
        r = client.get("/ready")
    finally:
        client.app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["detail"]["database"] == "down"


def test_ready_bounds_every_probe_and_closes_the_redis_client(client, monkeypatch):
    """A stalled dependency must turn into a 503, not a hung probe (review finding on #23)."""
    seen: dict[str, object] = {}

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            seen["closed"] = True

    def from_url(url, **kwargs):
        seen["kwargs"] = kwargs
        return FakeRedis()

    statements: list[str] = []

    class RecordingSession:
        def execute(self, stmt):
            statements.append(str(stmt))

        def rollback(self):
            seen["rolled_back"] = True

    monkeypatch.setattr(health.redis.Redis, "from_url", staticmethod(from_url))
    client.app.dependency_overrides[get_db] = lambda: RecordingSession()
    try:
        assert client.get("/ready").status_code == 200
    finally:
        client.app.dependency_overrides.clear()
    assert seen["kwargs"] == {
        "socket_connect_timeout": health.PROBE_TIMEOUT_S,
        "socket_timeout": health.PROBE_TIMEOUT_S,
    }
    assert seen["closed"] is True
    assert statements[0] == f"SET LOCAL statement_timeout = {health.PROBE_TIMEOUT_MS}"
    assert seen["rolled_back"] is True  # SET LOCAL never leaks past the probe


def test_docs_require_basic_auth(client):
    s = get_settings()
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/docs", auth=(s.docs_username, "wrong")).status_code == 401
    assert client.get("/docs", auth=(s.docs_username, s.docs_password)).status_code == 200
    spec = client.get("/openapi.json", auth=(s.docs_username, s.docs_password)).json()
    assert "/health" in spec["paths"] and "/ready" in spec["paths"]
    assert spec["info"]["description"]  # app.openapi(), not a bare get_openapi() rebuild


def test_docs_reject_non_ascii_credentials_with_401_not_500(client):
    r = client.get("/docs", auth=("evalstoné", "chänge-me"))
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Basic"
