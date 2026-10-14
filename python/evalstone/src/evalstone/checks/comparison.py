"""Pairwise comparison: is the candidate output better than a baseline's?

Judges are far more consistent at *preferring* than at scoring, and they prefer
whichever answer comes first unless you shuffle — so by default both orders are
judged and the verdicts combined (Evals 101, chapters 4 and 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from evalstone._json import sha256
from evalstone.checks._base import FunctionCheck, judge_model_for
from evalstone.checks.judge import DEFAULT_MAX_TOKENS, _json_text, explain_unparsed, extract_json
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.providers import ChatMessage, ProviderError
from evalstone.score import CheckKind, Context, Score
from evalstone.target import RecordedTarget, Target

SYSTEM = """You are comparing two answers to the same INPUT.

CRITERIA:
{rubric}

Decide which answer better satisfies the criteria. Ignore the order they are shown in,
their length, and formatting. Reply with ONLY a JSON object:
{{"winner": "A" | "B" | "tie", "reason": "<one sentence>"}}"""

USER = """INPUT:
{input}

ANSWER A:
{a}

ANSWER B:
{b}"""


def parse_winner(text: str) -> tuple[str, str]:
    data = extract_json(text)
    winner = str(data.get("winner", "")).strip().upper()
    if winner not in {"A", "B", "TIE"}:
        raise ValueError(f"judge winner must be A, B or tie, got {winner!r}")
    return winner, str(data.get("reason", "")).strip()


def pairwise(
    key: str,
    rubric: str,
    *,
    baseline: Target | Mapping[str, Any],
    model: str | None = None,
    both_orders: bool = True,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> FunctionCheck:
    """The candidate output beats the ``baseline`` output for the same sample.

    ``baseline`` is a Target (its outputs are produced per sample, cost counted) or a
    mapping of sample id → output. Each judged order scores 1 (candidate preferred),
    0.5 (tie) or 0 (baseline preferred); the value is their mean, so with both orders
    it is one of 1.0 / 0.75 / 0.5 / 0.25 / 0.0. Passes at 0.5 or above (wins or ties).
    """
    base_target: Target = baseline if isinstance(baseline, Target) else RecordedTarget(baseline)
    identity = {"v": 1, "rubric": rubric, "both_orders": both_orders}
    unpriced: list[str] = []  # models of this sample's calls that the price table lacks

    def ask(
        ctx: Context, chosen: str | None, sample_input: str, a: str, b: str
    ) -> tuple[str, str, float, float]:
        user = USER.format(input=sample_input, a=a, b=b)
        resp = ctx.providers.complete(
            chosen,
            {
                "system": SYSTEM.format(rubric=rubric.strip()),
                "messages": [ChatMessage(role="user", content=user)],
                "max_tokens": max_tokens,
            },
        )
        try:
            winner, reason = parse_winner(resp.text)
        except ValueError as exc:
            raise ValueError(explain_unparsed(exc, resp, max_tokens)) from None
        if resp.cost_usd is None:
            unpriced.append(resp.model)
        return winner, reason, resp.cost_usd or 0.0, resp.latency_ms

    def fn(sample: Sample, output: Output, ctx: Context) -> Score:
        if ctx.providers is None:
            return Score.errored("pairwise: no providers configured")
        unpriced.clear()
        chosen = judge_model_for(ctx, key, model)  # resolved once: the version AND the call
        try:
            resolved = "/".join(ctx.providers.split(chosen))
        except ProviderError as exc:
            return Score.errored(str(exc))
        version = sha256({**identity, "model": resolved})[:16]
        base = base_target.produce(sample)
        if base.error:
            return Score.errored(f"pairwise: baseline: {base.error}")
        text = _json_text(sample.input)
        cache_key = sha256({"p": version, "i": text, "c": output.text, "b": base.text})
        cached = ctx.cache.get(cache_key) if ctx.cache is not None else None
        if cached is not None:
            # The judge verdict is cached; the baseline was still produced (its cost counts).
            raw = {**(cached.raw or {}), "cached": True}
            return cached.model_copy(
                update={"cost_usd": base.cost_usd, "latency_ms": base.latency_ms, "raw": raw}
            )
        cost = base.cost_usd
        latency = 0.0
        points: list[float] = []
        reasons: list[str] = []
        try:
            orders = [("cand_first", output.text, base.text)]
            if both_orders:
                orders.append(("base_first", base.text, output.text))
            for label, a, b in orders:
                winner, reason, c, ms = ask(ctx, chosen, text, a, b)
                cost += c
                latency += ms
                candidate_is_a = label == "cand_first"
                if winner == "TIE":
                    points.append(0.5)
                elif (winner == "A") == candidate_is_a:
                    points.append(1.0)
                else:
                    points.append(0.0)
                reasons.append(reason)
        except ProviderError as exc:
            return Score.errored(str(exc), cost_usd=cost, latency_ms=latency)
        except ValueError as exc:
            return Score.errored(f"pairwise: {exc}", cost_usd=cost, latency_ms=latency)
        value = sum(points) / len(points)
        verdict = _label(value)
        score = Score(
            value=value,
            passed=value >= 0.5,
            reason=f"candidate {verdict}: " + " | ".join(r for r in reasons if r),
            cost_usd=cost,
            latency_ms=latency,
            raw={
                "points": points,
                "orders": len(points),
                "judge_version": version,
                "unpriced": bool(unpriced),
            },
        )
        if ctx.cache is not None:
            ctx.cache.set(cache_key, score)
        return score

    return FunctionCheck(key, fn, kind=CheckKind.COMPARISON)


def _label(value: float) -> str:
    if value == 1.0:
        return "wins"
    if value > 0.5:
        return "mostly wins"
    if value == 0.5:
        return "ties/split"
    if value > 0.0:
        return "mostly loses"
    return "loses"


__all__ = ["pairwise", "parse_winner"]
