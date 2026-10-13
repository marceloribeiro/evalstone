"""Org provider entries: encrypted keys, an SSRF guard on base_url, and the live test call.

Keys go in encrypted and never come out of the API: the only decrypt happens inside
`test_provider` / `build_registry`, in-process, to make the call.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from evalstone.providers import ChatMessage, ChatResponse, ProviderConfig, ProviderError, Providers
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_secret, encrypt_secret
from app.errors import Conflict, Invalid, NotFound
from app.models import ADAPTERS, JudgeSettings, Organization, Project, Provider

_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,49}$")
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "instance-data"}
KEY_REQUIRED_ADAPTERS = {"anthropic"}  # the SDK reads ANTHROPIC_API_KEY itself when given none
MIN_KEY_LEN_FOR_LAST4 = 8  # shorter keys get no hint at all
RESOLVE_TIMEOUT_S = 3.0
_resolver = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns-guard")


def _getaddrinfo(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def _resolve(host: str) -> list[str]:
    """Addresses a hostname resolves to, bounded by RESOLVE_TIMEOUT_S (tests patch this).

    Known limit: the HTTP client resolves again at call time, so a rebinding DNS name can
    pass here and point elsewhere later; the guard stops accidents and casual probing,
    not a hostile resolver. Pinning the resolved IP for the call is the stricter follow-up.
    """
    future = _resolver.submit(_getaddrinfo, host)
    try:
        return future.result(timeout=RESOLVE_TIMEOUT_S)
    except FutureTimeout as err:
        raise Invalid(
            f"base_url host {host!r} did not resolve within {RESOLVE_TIMEOUT_S:g}s"
        ) from err


def validate_base_url(url: str | None) -> str | None:
    """SSRF guard: the center dials this URL server-side with the org's key attached."""
    if url is None or url.strip() == "":
        return None
    url = url.strip()
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname  # also raises on a malformed IPv6 literal
    except ValueError as err:
        raise Invalid("base_url is not a valid URL") from err
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise Invalid("base_url must be an http(s) URL with a host")
    if parsed.username or parsed.password:
        raise Invalid("base_url must not embed credentials")
    host = hostname.lower()
    if get_settings().provider_allow_private_urls:
        return url.rstrip("/")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".internal"):
        raise Invalid(f"base_url host {host!r} is not allowed")
    try:
        addresses = [host] if _is_ip(host) else _resolve(host)
    except (OSError, UnicodeError) as err:  # UnicodeError: an over-long label, not an OSError
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
        p.encrypted_api_key = encrypt_secret(api_key)
        # a hint only when it cannot be the whole secret
        p.key_last4 = api_key[-4:] if len(api_key) >= MIN_KEY_LEN_FOR_LAST4 else None
    _reset_verdict(p)


def _reset_verdict(p: Provider) -> None:
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


_CALL_AFFECTING = {"api_key", "base_url", "headers", "max_tokens_param", "timeout_s"}


def update(db: Session, p: Provider, **fields) -> Provider:
    """`fields` holds only what the caller sent; an explicit None clears a nullable field."""
    touched = set(fields)
    if "api_key" in fields:
        _set_key(p, fields.pop("api_key"))
    if "base_url" in fields:
        p.base_url = validate_base_url(fields.pop("base_url"))
    if "prices" in fields:
        p.prices = _validate_prices(fields.pop("prices") or {})
    if "headers" in fields:
        p.headers = dict(fields.pop("headers") or {})
    if "max_tokens_param" in fields:
        p.max_tokens_param = fields.pop("max_tokens_param")  # None = back to host auto-detect
    if "timeout_s" in fields and fields["timeout_s"] is not None:
        p.timeout_s = fields.pop("timeout_s")
    if touched & _CALL_AFFECTING:
        _reset_verdict(p)  # the old verdict described a different endpoint/credentials
    db.commit()
    db.refresh(p)
    return p


def judge_settings_referencing(db: Session, p: Provider) -> list[Project]:
    """Projects whose judge settings route to `<p.name>/…`; deleting would strand them."""
    prefix = f"{p.name}/"
    rows = db.execute(
        select(JudgeSettings, Project)
        .join(Project, Project.id == JudgeSettings.project_id)
        .where(Project.organization_id == p.organization_id, Project.deleted_at.is_(None))
    ).all()
    hit: list[Project] = []
    for js, project in rows:
        models = [js.default_model, *list((js.overrides or {}).values())]
        if any(m and m.startswith(prefix) for m in models):
            hit.append(project)
    return hit


def soft_delete(db: Session, p: Provider) -> None:
    """Refuses while judge settings route to this name; purges the key from the row."""
    stranded = judge_settings_referencing(db, p)
    if stranded:
        slugs = ", ".join(sorted(x.slug for x in stranded))
        raise Conflict(f"provider '{p.name}' is used by judge settings of: {slugs}")
    p.deleted_at = datetime.now(UTC)
    p.encrypted_api_key, p.key_last4 = None, None
    _reset_verdict(p)
    db.commit()


# --- the registry the center uses to call a model ------------------------------------------


def provider_config(p: Provider, *, timeout_s: float | None = None) -> ProviderConfig:
    """Library config for one entry; the decrypted key lives only in this object, in-process."""
    if p.adapter in KEY_REQUIRED_ADAPTERS and not p.encrypted_api_key:
        raise Invalid(
            f"provider '{p.name}' ({p.adapter}) has no API key; the center never uses the "
            "server's own credentials for a tenant"
        )
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


class CenterRegistry:
    """`<name>/<model>` → that entry's own adapter and its own price table.

    One library `Providers` per entry, so two providers pricing the same bare model id
    (openai vs openrouter `gpt-x`) are each costed at their own rate.
    """

    def __init__(
        self,
        entries: list[Provider],
        *,
        timeout_s: float | None = None,
        default_model: str | None = None,
    ) -> None:
        self.default_model = default_model  # the project's default judge model, when known
        self._by_name: dict[str, Providers] = {}
        for p in entries:
            prices = {m: (r[0], r[1]) for m, r in (p.prices or {}).items()}
            self._by_name[p.name] = Providers(
                {p.name: provider_config(p, timeout_s=timeout_s)}, prices=prices
            )

    def split(self, model: str | None) -> tuple[str, str]:
        """`<provider>/<model>` → (name, bare) — what the library's judge check calls first."""
        model = model or self.default_model
        if not model:
            raise ProviderError("no model given and the project has no default judge model")
        if "/" not in model:
            raise ProviderError(f"model must be '<provider>/<model>', got {model!r}")
        name, _, bare = model.partition("/")
        if name not in self._by_name:
            raise ProviderError(f"unknown provider {name!r}")
        return name, bare

    def get(self, name: str) -> Any:
        if name not in self._by_name:
            raise ProviderError(f"unknown provider {name!r}")
        return self._by_name[name].get(name)

    def complete(self, model: str | None, request: dict[str, Any]) -> ChatResponse:
        name, bare = self.split(model)  # None → the project's default judge model
        return self._by_name[name].complete(f"{name}/{bare}", request)

    def close(self) -> None:
        for reg in self._by_name.values():
            reg.close()


def build_registry(
    entries: list[Provider], *, timeout_s: float | None = None, default_model: str | None = None
) -> CenterRegistry:
    return CenterRegistry(entries, timeout_s=timeout_s, default_model=default_model)


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
