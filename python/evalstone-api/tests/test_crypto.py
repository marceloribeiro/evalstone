import pytest
from cryptography.fernet import Fernet

from app import crypto
from app.config import Settings


def test_round_trip_and_ciphertext_is_opaque():
    token = crypto.encrypt_secret("sk-live-abc")
    assert "sk-live" not in token
    assert crypto.decrypt_secret(token) == "sk-live-abc"


def test_rotated_key_is_a_422_with_a_hint(monkeypatch):
    token = crypto.encrypt_secret("sk-live-abc")
    monkeypatch.setattr(crypto, "_fernet", lambda: Fernet(Fernet.generate_key()))
    with pytest.raises(crypto.UndecryptableKey) as err:
        crypto.decrypt_secret(token)
    assert err.value.status == 422 and "PROVIDER_CREDS_KEY" in err.value.detail


def test_production_requires_a_provider_creds_key():
    with pytest.raises(ValueError, match="PROVIDER_CREDS_KEY"):
        Settings(app_env="production", docs_password="s3cret", jwt_secret="a" * 40)
    ok = Settings(
        app_env="production",
        docs_password="s3cret",
        jwt_secret="a" * 40,
        provider_creds_key=Fernet.generate_key().decode(),
    )
    assert ok.provider_creds_key


def test_production_refuses_a_malformed_provider_creds_key():
    with pytest.raises(ValueError, match="not a valid Fernet key"):
        Settings(
            app_env="production",
            docs_password="s3cret",
            jwt_secret="a" * 40,
            provider_creds_key="my-secret-string",
        )
