"""LLM-as-judge: a rubric, a small scale, structured JSON back, cached by content.

Follows the practice in Evals 101 chapter 6: specific criteria, a defined
scale, the reference included only when asked for, temperature left at the
provider default (the cache makes re-runs free anyway), and **an error is
never a pass** (timeouts, refusals, unparseable verdicts → ``Score.errored``).
"""

from __future__ import annotations

import json
import re
from typing import Any

from evalstone._json import dumps, sha256
from evalstone.checks._base import FunctionCheck, judge_model_for
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.providers import ChatMessage, ChatResponse, ProviderError
from evalstone.score import CheckKind, Context, Score

PROMPT_VERSION = 1

# Room for a verdict plus a long reason: 256 cut real Haiku 5.5 replies mid-reason
# (4 of 10 on the rag-bot demo). The cap only bounds a runaway; it is not in the version.
DEFAULT_MAX_TOKENS = 1024

# How each adapter reports "stopped at the token cap": OpenAI-compatible, Anthropic, Gemini.
TRUNCATED_STOP_REASONS = frozenset({"length", "max_tokens"})

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
    return value if isinstance(value, str) else dumps(value, indent=2)


def extract_json(text: str) -> dict[str, Any]:
    """The first JSON object in a model reply, tolerating prose around it."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in judge reply: {text[:120]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in judge reply: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ValueError(f"judge reply is not a JSON object: {text[:120]!r}")
    return data


def parse_verdict(text: str, scale: int) -> tuple[int, str]:
    """Pull ``{"score": n, "reason": ...}`` out of a model reply."""
    data = extract_json(text)
    try:
        score = round(float(data["score"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"judge reply has no numeric score: {data!r}"[:200]) from None
    if not 1 <= score <= scale:
        raise ValueError(f"judge score {score} outside 1..{scale}")
    return score, str(data.get("reason", "")).strip()


def explain_unparsed(exc: ValueError, resp: ChatResponse, max_tokens: int) -> str:
    """The parse error, or the real cause when the provider stopped at the token cap."""
    if (resp.stop_reason or "").lower() in TRUNCATED_STOP_REASONS:
        return (
            f"reply truncated at max_tokens={max_tokens} before the verdict was complete; "
            "raise the check's max_tokens"
        )
    return str(exc)


class JudgeCheck(FunctionCheck):
    """A ``FunctionCheck`` whose function calls a model; exposes the judge version hash."""

    def __init__(
        self,
        key: str,
        fn: Any,
        *,
        version_hash: str,
        model: str | None,
        rubric: str,
        scale: int,
        pass_at: float,
    ):
        super().__init__(key, fn, kind=CheckKind.JUDGE)
        # rubric + scale + prompt version; the resolved model is folded in at run time
        self.version_hash = version_hash
        self.model = model
        self.rubric = rubric
        self.scale = scale
        self.pass_at = pass_at


def judge(
    key: str,
    rubric: str,
    *,
    model: str | None = None,
    scale: int = 5,
    pass_level: int | None = None,
    threshold: float | None = None,
    include_reference: bool = False,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> JudgeCheck:
    """Grade an output against ``rubric`` with a model.

    The model answers with a level ``n`` in ``1..scale``; ``value = (n-1)/(scale-1)``.
    The verdict passes at or above ``pass_level`` (a rubric level; default: the
    second-highest level — 4 on a 1-5 scale — and the top level on a 1-2 yes/no
    scale) or, equivalently, at or above ``threshold`` (a 0..1 fraction of the
    normalised value). Give one or the other.
    ``include_reference`` adds ``sample.expected`` to the prompt — only do this when
    similarity to the reference is the criterion.
    """
    if scale < 2:
        raise ValueError("scale must be at least 2")
    if pass_level is not None and threshold is not None:
        raise ValueError("give pass_level (a rubric level) or threshold (0..1), not both")
    if threshold is not None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"threshold must be a 0..1 fraction of the normalised score, got {threshold}; "
                "to pass at a rubric level use pass_level="
            )
        pass_at = threshold
    else:
        level = pass_level if pass_level is not None else (scale - 1 if scale >= 3 else scale)
        if not 1 <= level <= scale:
            raise ValueError(f"pass_level must be within 1..{scale}, got {level}")
        pass_at = (level - 1) / (scale - 1)
    identity = {"v": PROMPT_VERSION, "rubric": rubric, "scale": scale, "ref": include_reference}
    version_hash = sha256(identity)[:16]

    def fn(sample: Sample, output: Output, ctx: Context) -> Score:
        providers = ctx.providers
        if providers is None:
            return Score.errored("judge: no providers configured (ctx.providers is None)")
        chosen = judge_model_for(ctx, key, model)
        try:
            resolved = "/".join(providers.split(chosen))
        except ProviderError as exc:
            return Score.errored(str(exc))
        judge_version = sha256({**identity, "model": resolved})[:16]
        reference = ""
        if include_reference and sample.expected is not None:
            reference = (
                f"\nREFERENCE (what a good answer must satisfy):\n{_json_text(sample.expected)}\n"
            )
        user = USER_TEMPLATE.format(
            input=_json_text(sample.input), reference=reference, output=output.text
        )
        system = SYSTEM_TEMPLATE.format(rubric=rubric.strip(), scale=scale)

        def to_score(n: int, reason: str, *, raw: dict[str, Any], cost: float, ms: float) -> Score:
            # value/passed are derived here, so a cached raw verdict serves every threshold.
            value = (n - 1) / (scale - 1)
            return Score(
                value=value,
                passed=value >= pass_at,
                reason=f"{n}/{scale}: {reason}" if reason else f"{n}/{scale}",
                cost_usd=cost,
                latency_ms=ms,
                raw={**raw, "score": n, "scale": scale, "judge_version": judge_version},
            )

        # The cache holds the model's raw verdict (level + reason), keyed by the
        # resolved judge version and the exact prompt — never a derived pass/fail.
        cache_key = sha256({"j": judge_version, "u": user})
        cached = ctx.cache.get(cache_key) if ctx.cache is not None else None
        if cached is not None and cached.raw and "score" in cached.raw:
            raw = {k: v for k, v in cached.raw.items() if k not in {"score", "scale"}}
            return to_score(
                int(cached.raw["score"]),
                _verdict_reason(cached),
                raw={**raw, "cached": True},
                cost=0.0,
                ms=0.0,
            )
        try:
            resp = providers.complete(
                chosen,
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
                f"judge: {explain_unparsed(exc, resp, max_tokens)}",
                cost_usd=resp.cost_usd or 0.0,
                latency_ms=resp.latency_ms,
            )
        score = to_score(
            n,
            reason,
            raw={
                "model": resp.model,
                "tokens": [resp.input_tokens, resp.output_tokens],
                "unpriced": resp.cost_usd is None,
                "verdict_reason": reason,
            },
            cost=resp.cost_usd or 0.0,
            ms=resp.latency_ms,
        )
        if ctx.cache is not None:
            ctx.cache.set(cache_key, score)
        return score

    return JudgeCheck(
        key, fn, version_hash=version_hash, model=model, rubric=rubric, scale=scale, pass_at=pass_at
    )


def _verdict_reason(score: Score) -> str:
    return str((score.raw or {}).get("verdict_reason", ""))


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "PROMPT_VERSION",
    "JudgeCheck",
    "explain_unparsed",
    "extract_json",
    "judge",
    "parse_verdict",
]
