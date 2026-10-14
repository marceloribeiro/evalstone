"""Attach a project to an Evalstone center (``center:`` in evalstone.yaml).

Attached, judge calls go through the center's model proxy, which resolves the model
from the project's judge settings and dials the provider with the organization's key
server-side, so no judge key lives on the machine running the suite. Prompt targets
(the system under test) are NOT proxied: they keep using the local ``providers:`` and
their env keys. The judge cache lives in the center (one verdict serves every
machine), ``human`` checks look labels up there, and every ``evalstone run`` pushes
its report. ``judges:`` in the YAML is ignored while attached; ``providers:`` still
serves prompt targets.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel

from evalstone.providers import ChatRequest, ChatResponse, ProviderError
from evalstone.score import MemoryCache, Score

DEFAULT_KEY_ENV = "EVALSTONE_API_KEY"


class CenterConfig(BaseModel):
    url: str
    project: str  # the center project id (uuid)
    api_key_env: str = DEFAULT_KEY_ENV  # an ingest key (es_…) or a user token
    timeout: float = 120.0  # a judge call waits on the provider behind the proxy
    cache_timeout: float = 10.0  # cache and label lookups: a slow center is a miss, fast
    push_runs: bool = True  # `evalstone run` pushes its report
    cache: bool = True  # judge verdicts read/written in the center

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None


class CenterError(ProviderError):
    """The center refused or could not serve a request."""


class CenterClient:
    """Thin HTTP client for the center's project endpoints."""

    def __init__(self, config: CenterConfig, *, client: Any = None) -> None:
        self.config = config
        key = config.api_key()
        if not key:
            raise CenterError(
                f"center: no API key — set {config.api_key_env} (an ingest key from the "
                "project's settings) in the environment"
            )
        self._client = client or httpx.Client(
            base_url=config.url.rstrip("/"),
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {key}"},
        )
        self._owns = client is None

    def close(self) -> None:
        if self._owns:
            self._client.close()

    # ── transport ────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CenterError(f"center: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _detail(resp: httpx.Response) -> str:
        try:
            body = resp.json()
        except ValueError:
            body = None
        detail = body.get("detail") if isinstance(body, dict) else body
        return str(detail)[:300] if detail else resp.text[:300]

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise CenterError(f"center: HTTP {resp.status_code}: {self._detail(resp)}")
        try:
            return resp.json()
        except ValueError as exc:
            raise CenterError(f"center: non-JSON response: {resp.text[:200]!r}") from exc

    def _p(self, suffix: str) -> str:
        return f"/projects/{self.config.project}{suffix}"

    # ── endpoints ────────────────────────────────────────────────────────

    def whoami(self) -> dict[str, Any]:
        return self._json("GET", "/ingest/whoami")

    def judge_settings(self) -> dict[str, Any]:
        return self._json("GET", self._p("/judge-settings"))

    def complete(
        self, model: str | None, request: ChatRequest, *, check_key: str | None = None
    ) -> ChatResponse:
        """The proxy call: `model` is `<provider>/<model>` (or None → the center picks)."""
        body = {
            "model": model,
            "check_key": check_key,
            "system": request.system,
            "messages": [m.model_dump() for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        data = self._json("POST", self._p("/model/complete"), json=body)
        return ChatResponse.model_validate(data)

    def cache_get(self, key: str) -> Score | None:
        resp = self._request(
            "GET", self._p(f"/judge-cache/{key}"), timeout=self.config.cache_timeout
        )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CenterError(f"center: HTTP {resp.status_code}: {self._detail(resp)}")
        return Score.model_validate(resp.json()["score"])

    def cache_set(self, key: str, score: Score) -> None:
        judge_version = (
            (score.raw or {}).get("judge_version") if isinstance(score.raw, dict) else None
        )
        self._json(
            "PUT",
            self._p(f"/judge-cache/{key}"),
            json={"score": score.model_dump(mode="json"), "judge_version": judge_version},
            timeout=self.config.cache_timeout,
        )

    def label_lookup(
        self, sample_id: str, output_hash: str, check: str | None
    ) -> dict[str, Any] | None:
        params = {"sample_key": sample_id, "output_hash": output_hash}
        if check is not None:
            params["check"] = check
        resp = self._request(
            "GET", self._p("/labels/lookup"), params=params, timeout=self.config.cache_timeout
        )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CenterError(f"center: HTTP {resp.status_code}: {self._detail(resp)}")
        return resp.json()

    def push_run(self, report: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Store a run report; returns (run, created) — 200 means the center had it already."""
        resp = self._request("POST", self._p("/runs"), json=report)
        if resp.status_code >= 400:
            raise CenterError(f"center: HTTP {resp.status_code}: {self._detail(resp)}")
        return resp.json(), resp.status_code == 201


# ── the Providers surface, backed by the proxy ───────────────────────────


class RemoteProvider:
    """One named provider entry of the center (a `Provider` whose calls go through the proxy)."""

    def __init__(self, name: str, client: CenterClient) -> None:
        self.name = name
        self._client = client

    def complete(self, request: ChatRequest) -> ChatResponse:
        return self._client.complete(f"{self.name}/{request.model}", request)


class CenterProviders:
    """Drop-in for ``evalstone.providers.Providers`` when a project is attached.

    ``split``/``get``/``complete`` match the registry the judge check and prompt targets
    call; the default model comes from the center's judge settings, so a check without
    its own ``model`` resolves there.
    """

    def __init__(self, client: CenterClient, *, default_model: str | None = None) -> None:
        self.client = client
        self.default_model = default_model
        self._instances: dict[str, RemoteProvider] = {}

    def split(self, model: str | None) -> tuple[str, str]:
        model = model or self.default_model
        if not model:
            raise ProviderError(
                "no model given and the center project has no default judge model "
                "(set it in the project's judge settings)"
            )
        if "/" not in model:
            raise ProviderError(f"model must be '<provider>/<model>', got {model!r}")
        name, _, bare = model.partition("/")
        return name, bare

    def get(self, name: str) -> RemoteProvider:
        if name not in self._instances:
            self._instances[name] = RemoteProvider(name, self.client)
        return self._instances[name]

    def complete(self, model: str | None, request_without_model: dict[str, Any]) -> ChatResponse:
        name, bare = self.split(model)
        req = ChatRequest(model=bare, **request_without_model)
        return self.client.complete(f"{name}/{bare}", req)

    def close(self) -> None:
        self.client.close()


class CenterCache:
    """A ``ScoreCache`` in the center, with an in-process layer so a run asks once per key.

    A center hiccup is a miss (a judge then pays for the call); it never fails the run.
    """

    def __init__(self, client: CenterClient) -> None:
        self._client = client
        self._local = MemoryCache()
        self.errors: list[str] = []

    def get(self, key: str) -> Score | None:
        hit = self._local.get(key)
        if hit is not None:
            return hit
        try:
            score = self._client.cache_get(key)
        except Exception as exc:
            self.errors.append(f"{type(exc).__name__}: {exc}")
            return None
        if score is not None:
            self._local.set(key, score)
        return score

    def set(self, key: str, score: Score) -> None:
        self._local.set(key, score)
        try:
            self._client.cache_set(key, score)
        except Exception as exc:
            self.errors.append(f"{type(exc).__name__}: {exc}")


__all__ = [
    "DEFAULT_KEY_ENV",
    "CenterCache",
    "CenterClient",
    "CenterConfig",
    "CenterError",
    "CenterProviders",
    "RemoteProvider",
]
