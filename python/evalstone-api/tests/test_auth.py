import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.errors import Unauthorized
from app.security import create_token, decode_token
from app.services import users as user_service


def test_register_returns_user_and_a_usable_token(client, register):
    headers, user = register("New@Example.com", first_name="Ada")
    assert user["email"] == "new@example.com"  # normalised
    assert "password" not in user and "password_hash" not in user
    me = client.get("/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["id"] == user["id"] and me.json()["first_name"] == "Ada"


def test_register_rejects_duplicates_case_insensitively(client, register):
    register("dup@example.com")
    r = client.post("/auth/register", json={"email": "DUP@example.com", "password": "password123"})
    assert r.status_code == 409


def test_register_validates_password_length(client):
    short = client.post("/auth/register", json={"email": "a@b.co", "password": "short"})
    assert short.status_code == 422
    long = client.post("/auth/register", json={"email": "a@b.co", "password": "x" * 73})
    assert long.status_code == 422  # bcrypt's 72-byte limit is enforced, not silently truncated


def test_login_and_bad_credentials(client, register):
    register("login@example.com", password="correct-horse")
    ok = client.post(
        "/auth/login", json={"email": "LOGIN@example.com", "password": "correct-horse"}
    )
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/auth/login", json={"email": "login@example.com", "password": "wrong"})
    assert bad.status_code == 401
    assert bad.headers["WWW-Authenticate"] == "Bearer"
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "x" * 8})
    assert unknown.status_code == 401


def test_me_requires_a_valid_token(client, register):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_token_round_trip(register):
    _, user = register("t@example.com")
    uid = uuid.UUID(user["id"])
    assert decode_token(create_token(uid)) == uid


def test_tokens_are_rejected_when_tampered_expired_or_malformed(client, register):
    _, user = register("t2@example.com")
    s = get_settings()
    other_secret = jwt.encode({"sub": user["id"]}, "x" * 40, algorithm="HS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {other_secret}"}).status_code == 401
    unsigned = jwt.encode({"sub": user["id"]}, key="", algorithm="none")
    assert client.get("/me", headers={"Authorization": f"Bearer {unsigned}"}).status_code == 401
    expired = jwt.encode(
        {"sub": user["id"], "exp": datetime.now(UTC) - timedelta(seconds=1)},
        s.jwt_secret,
        algorithm="HS256",
    )
    assert client.get("/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    not_a_uuid = jwt.encode({"sub": "nope"}, s.jwt_secret, algorithm="HS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {not_a_uuid}"}).status_code == 401
    with pytest.raises(Unauthorized):
        decode_token("garbage")


def test_register_rejects_a_multibyte_password_over_72_bytes(client):
    r = client.post("/auth/register", json={"email": "u@example.com", "password": "é" * 40})
    assert r.status_code == 422  # 40 chars, 80 bytes: bcrypt 5 would raise → 500 (#24 review)
    assert "bytes" in r.text
    ok = client.post("/auth/register", json={"email": "u@example.com", "password": "é" * 36})
    assert ok.status_code == 201


def test_unknown_email_login_still_runs_a_password_check(client, monkeypatch):
    """No timing oracle: a miss on the email costs a bcrypt verify like a wrong password (#24)."""
    calls: list[str] = []
    real = user_service.verify_password
    monkeypatch.setattr(
        user_service, "verify_password", lambda p, h: (calls.append(h), real(p, h))[1]
    )
    r = client.post("/auth/login", json={"email": "ghost@example.com", "password": "whatever1"})
    assert r.status_code == 401 and len(calls) == 1


def test_service_register_hashes_and_authenticates(db):
    u = user_service.register(db, email="Svc@Example.com", password="password123")
    assert u.email == "svc@example.com"
    assert u.password_hash != "password123" and u.password_hash.startswith("$2b$")
    assert user_service.authenticate(db, email="svc@example.com", password="password123").id == u.id
