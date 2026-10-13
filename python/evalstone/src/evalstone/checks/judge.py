"""LLM-as-judge: a rubric, a small scale, structured JSON back, cached by content.

Follows the practice in Evals 101 chapter 6: specific criteria, a defined
scale, the reference included only when asked for, temperature left at the
provider default (the cache makes re-runs free anyway), and **an error is
never a pass** (timeouts, refusals, unparseable verdicts → ``Score.errored``).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from evalstone._json import canonical
from evalstone.checks._base import FunctionCheck
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.providers import ChatMessage, ProviderError
from evalstone.score import CheckKind, Context, Score

PROMPT_VERSION = 1

SYSTEM_TEMPLATE = """You are a strict evaluator grading one answer produced by an AI system.

RUBRIC:
{rubric}

Score the answer from 1 to {scale} according to the rubric ({scale} = fully meets it, 1 = fails it).
Ignore formatting and length unless the rubric mentions them.
Reply with ONLY a JSON object: {{"score": <integer 1-{scale}>, "reason": "<one sentence>"}}"""

USER_TEMPLATE = """INPUT:
{input}
{reference}
ANSWER:
{output}"""


def _json_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def parse_verdict(text: str, scale: int) -> tuple[int, str]:
    """Pull ``{"score": n, "reason": ...}`` out of a model reply, tolerating prose around it."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in judge reply: {text[:120]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in judge reply: {exc.msg}") from None
    try:
        score = round(float(data["score"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"judge reply has no numeric score: {data!r}"[:200]) from None
    if not 1 <= score <= scale:
        raise ValueError(f"judge score {score} outside 1..{scale}")
    return score, str(data.get("reason", "")).strip()


class JudgeCheck(FunctionCheck):
    """A ``FunctionCheck`` whose function calls a model; exposes the judge version hash."""

    def __init__(self, key: str, fn: Any, *, version_hash: str, model: str | None, rubric: str):
        super().__init__(key, fn, kind=CheckKind.JUDGE)
        self.version_hash = version_hash
        self.model = model
        self.rubric = rubric


def judge(
    key: str,
    rubric: str,
    *,
    model: str | None = None,
    scale: int = 5,
    threshold: float | None = None,
    include_reference: bool = False,
    max_tokens: int = 256,
) -> JudgeCheck:
    """Grade an output against ``rubric`` with a model.

    score = (n-1)/(scale-1); passes at or above ``threshold``, which defaults to the
    second-highest level (4 on a 1-5 scale).
    ``include_reference`` adds ``sample.expected`` to the prompt — only do this when
    similarity to the reference is the criterion.
    """
    if scale < 2:
        raise ValueError("scale must be at least 2")
    pass_at = threshold if threshold is not None else (scale - 2) / (scale - 1)
    identity = {
        "v": PROMPT_VERSION,
        "rubric": rubric,
        "model": model,
        "scale": scale,
        "ref": include_reference,
    }
    version_hash = hashlib.sha256(canonical(identity).encode()).hexdigest()[:16]

    def fn(sample: Sample, output: Output, ctx: Context) -> Score:
        providers = ctx.providers
        if providers is None:
            return Score.errored("judge: no providers configured (ctx.providers is None)")
        reference = ""
        if include_reference and sample.expected is not None:
            reference = (
                f"\nREFERENCE (what a good answer must satisfy):\n{_json_text(sample.expected)}\n"
            )
        user = USER_TEMPLATE.format(
            input=_json_text(sample.input), reference=reference, output=output.text
        )
        system = SYSTEM_TEMPLATE.format(rubric=rubric.strip(), scale=scale)
        cache_key = hashlib.sha256(canonical({"j": version_hash, "u": user}).encode()).hexdigest()
        cached = ctx.cache.get(cache_key) if ctx.cache is not None else None
        if cached is not None:
            raw = {**(cached.raw or {}), "cached": True}
            return cached.model_copy(update={"cost_usd": 0.0, "latency_ms": 0.0, "raw": raw})
        try:
            resp = providers.complete(
                model,
                {
                    "system": system,
                    "messages": [ChatMessage(role="user", content=user)],
                    "max_tokens": max_tokens,
                },
            )
        except ProviderError as exc:
            return Score.errored(str(exc))
        try:
            n, reason = parse_verdict(resp.text, scale)
        except ValueError as exc:
            return Score.errored(
                f"judge: {exc}", cost_usd=resp.cost_usd or 0.0, latency_ms=resp.latency_ms
            )
        value = (n - 1) / (scale - 1)
        score = Score(
            value=value,
            passed=value >= pass_at,
            reason=f"{n}/{scale}: {reason}" if reason else f"{n}/{scale}",
            cost_usd=resp.cost_usd or 0.0,
            latency_ms=resp.latency_ms,
            raw={
                "score": n,
                "scale": scale,
                "model": resp.model,
                "tokens": [resp.input_tokens, resp.output_tokens],
                "unpriced": resp.cost_usd is None,
            },
        )
        if ctx.cache is not None:
            ctx.cache.set(cache_key, score)
        return score

    return JudgeCheck(key, fn, version_hash=version_hash, model=model, rubric=rubric)


__all__ = ["PROMPT_VERSION", "JudgeCheck", "judge", "parse_verdict"]
