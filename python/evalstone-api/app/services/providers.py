"""Org provider entries: encrypted keys, an SSRF guard on base_url, and the live test call.

Keys go in encrypted and never come out of the API: the only decrypt happens inside
`test_provider` / `build_registry`, in-process, to make the call.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from evalstone.providers import ChatMessage, ProviderConfig, ProviderError, Providers
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_secret, encrypt_secret
from app.errors import Conflict, Invalid, NotFound
from app.models import ADAPTERS, Organization, Provider

_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,49}$")
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "instance-data"}


def _resolve(host: str) -> list[str]:
    """Addresses a hostname resolves to (tests patch this; literal IPs skip DNS)."""
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def validate_base_url(url: str | None) -> str | None:
    """SSRF guard: the center dials this URL server-side with the org's key attached."""
    if url is None or url.strip() == "":
        return None
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise Invalid("base_url must be an http(s) URL with a host")
    if parsed.username or parsed.password:
        raise Invalid("base_url must not embed credentials")
    host = parsed.hostname.lower()
    if get_settings().provider_allow_private_urls:
        return url.rstrip("/")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".internal"):
        raise Invalid(f"base_url host {host!r} is not allowed")
    try:
        addresses = [host] if _is_ip(host) else _resolve(host)
    except OSError as err:
        raise Invalid(f"base_url host {host!r} does not resolve") from err
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if not ip.is_global:
            raise Invalid(
                f"base_url host {host!r} resolves to a private or reserved address ({addr}); "
                "set PROVIDER_ALLOW_PRIVATE_URLS=true for a self-hosted gateway"
            )
    return url.rstrip("/")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _validate_prices(prices: dict) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for model, rates in (prices or {}).items():
        if (
            not isinstance(rates, (list, tuple))
            or len(rates) != 2
            or not all(isinstance(r, int | float) and r >= 0 for r in rates)
        ):
            raise Invalid(f"prices[{model!r}] must be [input_usd_per_1m, output_usd_per_1m]")
        out[str(model)] = [float(rates[0]), float(rates[1])]
    return out


def list_providers(db: Session, org: Organization) -> list[Provider]:
    return list(
        db.scalars(
            select(Provider)
            .where(Provider.organization_id == org.id, Provider.deleted_at.is_(None))
            .order_by(Provider.created_at)
        ).all()
    )


def get_provider(db: Session, org: Organization, provider_id: uuid.UUID) -> Provider:
    p = db.get(Provider, provider_id)
    if p is None or p.deleted_at is not None or p.organization_id != org.id:
        raise NotFound("provider not found")
    return p


def get_by_name(db: Session, org_id: uuid.UUID, name: str) -> Provider | None:
    return db.scalar(
        select(Provider).where(
            Provider.organization_id == org_id,
            Provider.name == name,
            Provider.deleted_at.is_(None),
        )
    )


def _set_key(p: Provider, api_key: str | None) -> None:
    if api_key is None:
        return  # not mentioned: keep
    api_key = api_key.strip()
    if api_key == "":
        p.encrypted_api_key, p.key_last4 = None, None  # explicit clear (keyless gateway)
    else:
        p.encrypted_api_key, p.key_last4 = encrypt_secret(api_key), api_key[-4:]
    p.verified_ok, p.last_verified_at, p.last_error = None, None, None


def create(
    db: Session,
    *,
    org: Organization,
    name: str,
    adapter: str,
    api_key: str | None = None,
    base_url: str | None = None,
    headers: dict | None = None,
    prices: dict | None = None,
    timeout_s: float = 60.0,
    max_tokens_param: str | None = None,
) -> Provider:
    if not _NAME.match(name):
        raise Invalid("name must be lowercase letters, digits, '-' or '_' (max 50)")
    if adapter not in ADAPTERS:
        raise Invalid(f"adapter must be one of {', '.join(ADAPTERS)}")
    if get_by_name(db, org.id, name) is not None:
        raise Conflict(f"provider '{name}' already exists in this organization")
    p = Provider(
        organization_id=org.id,
        name=name,
        adapter=adapter,
        base_url=validate_base_url(base_url),
        headers=dict(headers or {}),
        prices=_validate_prices(prices or {}),
        timeout_s=timeout_s,
        max_tokens_param=max_tokens_param,
    )
    _set_key(p, api_key)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update(db: Session, p: Provider, **fields) -> Provider:
    if "api_key" in fields:
        _set_key(p, fields.pop("api_key"))
    if "base_url" in fields:
        p.base_url = validate_base_url(fields.pop("base_url"))
        p.verified_ok, p.last_verified_at, p.last_error = None, None, None
    if "prices" in fields:
        p.prices = _validate_prices(fields.pop("prices") or {})
    if "headers" in fields:
        p.headers = dict(fields.pop("headers") or {})
    for k, v in fields.items():
        if v is not None:
            setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


def soft_delete(db: Session, p: Provider) -> None:
    p.deleted_at = datetime.now(UTC)
    db.commit()


# --- the registry the center uses to call a model ------------------------------------------


def provider_config(p: Provider, *, timeout_s: float | None = None) -> ProviderConfig:
    """Library config for one entry; the decrypted key lives only in this object, in-process."""
    api_key = decrypt_secret(p.encrypted_api_key) if p.encrypted_api_key else None
    return ProviderConfig(
        adapter=p.adapter,
        base_url=p.base_url,
        api_key=api_key,
        api_key_env="",  # a center entry never falls back to the server's environment
        headers=dict(p.headers or {}),
        timeout=timeout_s or p.timeout_s,
        max_tokens_param=p.max_tokens_param,
    )


def build_registry(entries: list[Provider], *, timeout_s: float | None = None) -> Providers:
    prices = {}
    for p in entries:
        prices.update({m: (r[0], r[1]) for m, r in (p.prices or {}).items()})
    return Providers(
        {p.name: provider_config(p, timeout_s=timeout_s) for p in entries}, prices=prices
    )


def test_provider(db: Session, p: Provider, *, model: str) -> dict:
    """One tiny call through the library adapter; records the verdict on the row."""
    registry = build_registry([p], timeout_s=get_settings().provider_test_timeout_s)
    request = {
        "messages": [ChatMessage(role="user", content="Reply with the single word OK.")],
        "max_tokens": 5,
    }
    result: dict
    try:
        resp = registry.complete(f"{p.name}/{model}", request)
        result = {
            "ok": True,
            "model": resp.model,
            "latency_ms": round(resp.latency_ms, 1),
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cost_usd": resp.cost_usd,
            "error": None,
        }
        p.verified_ok, p.last_error = True, None
    except ProviderError as err:
        result = {
            "ok": False,
            "model": model,
            "latency_ms": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": None,
            "error": str(err)[:500],
        }
        p.verified_ok, p.last_error = False, result["error"]
    finally:
        registry.close()
    p.last_verified_at = datetime.now(UTC)
    db.commit()
    return result
