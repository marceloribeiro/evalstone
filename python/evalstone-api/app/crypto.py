"""The one place provider API keys are encrypted and decrypted (D-2026-10-13-a).

`PROVIDER_CREDS_KEY` must stay stable forever: rotating it makes every stored key
undecryptable. Development and test derive a fixed key when the setting is empty.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.errors import Invalid

_DEV_PASSPHRASE = "evalstone-dev-provider-creds-key"


class UndecryptableKey(Invalid):
    """The stored ciphertext does not match PROVIDER_CREDS_KEY (rotated key, dev→prod mismatch)."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().provider_creds_key
    if not key:
        # only reachable in development/test — Settings refuses an empty key elsewhere
        digest = hashlib.sha256(_DEV_PASSPHRASE.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    try:
        return Fernet(key.encode())
    except ValueError as err:
        raise RuntimeError("PROVIDER_CREDS_KEY is not a valid Fernet key") from err


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as err:
        raise UndecryptableKey(
            "stored API key cannot be decrypted (PROVIDER_CREDS_KEY changed?); re-enter the key"
        ) from err
