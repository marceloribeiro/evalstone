"""Password hashing (bcrypt) and JWT minting/verification (HS256)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings
from app.errors import Unauthorized

ALGORITHM = "HS256"
INGEST_KEY_PREFIX = "es_"


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_expires_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as err:
        raise Unauthorized("invalid or expired token") from err


def new_ingest_key() -> tuple[str, str, str]:
    """(secret, sha256 hex, display prefix). The secret is shown once and never stored."""
    secret = INGEST_KEY_PREFIX + secrets.token_urlsafe(32)
    return secret, hash_ingest_key(secret), secret[:12]


def hash_ingest_key(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
