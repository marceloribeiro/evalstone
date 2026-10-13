"""Pairwise comparison: is the candidate output better than a baseline's?

Judges are far more consistent at *preferring* than at scoring, and they prefer
whichever answer comes first unless you shuffle — so by default both orders are
judged and the verdicts combined (Evals 101, chapters 4 and 6).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from evalstone._json import canonical
from evalstone.checks._base import FunctionCheck
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
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in judge reply: {text[:120]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in judge reply: {exc.msg}") from None
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
    max_tokens: int = 256,
) -> FunctionCheck:
    """The candidate output beats the ``baseline`` output for the same sample.

    ``baseline`` is a Target (its outputs are produced per sample, cost counted) or a
    mapping of sample id → output. Score: 1.0 wins (both orders), 0.5 split or tie,
    0.0 loses. Passes when the candidate wins or ties.
    """
    base_target: Target = baseline if isinstance(baseline, Target) else RecordedTarget(baseline)
    identity = canonical({"v": 1, "rubric": rubric, "model": model})
    version = hashlib.sha256(identity.encode()).hexdigest()[:16]

    def ask(ctx: Context, sample_input: str, a: str, b: str) -> tuple[str, str, float, float]:
        user = USER.format(input=sample_input, a=a, b=b)
        resp = ctx.providers.complete(
            model,
            {
                "system": SYSTEM.format(rubric=rubric.strip()),
                "messages": [ChatMessage(role="user", content=user)],
                "max_tokens": max_tokens,
            },
        )
        winner, reason = parse_winner(resp.text)
        return winner, reason, resp.cost_usd or 0.0, resp.latency_ms

    def fn(sample: Sample, output: Output, ctx: Context) -> Score:
        if ctx.providers is None:
            return Score.errored("pairwise: no providers configured")
        base = base_target.produce(sample)
        if base.error:
            return Score.errored(f"pairwise: baseline: {base.error}")
        text = sample.input if isinstance(sample.input, str) else json.dumps(sample.input, indent=2)
        key_material = canonical({"p": version, "i": text, "c": output.text, "b": base.text})
        cache_key = hashlib.sha256(key_material.encode()).hexdigest()
        cached = ctx.cache.get(cache_key) if ctx.cache is not None else None
        if cached is not None:
            return cached.model_copy(update={"cost_usd": 0.0, "latency_ms": 0.0})
        cost = base.cost_usd
        latency = 0.0
        points: list[float] = []
        reasons: list[str] = []
        try:
            orders = [("cand_first", output.text, base.text)]
            if both_orders:
                orders.append(("base_first", base.text, output.text))
            for label, a, b in orders:
                winner, reason, c, ms = ask(ctx, text, a, b)
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
        verdict = "wins" if value == 1.0 else "ties/split" if value == 0.5 else "loses"
        score = Score(
            value=value,
            passed=value >= 0.5,
            reason=f"candidate {verdict}: " + " | ".join(r for r in reasons if r),
            cost_usd=cost,
            latency_ms=latency,
            raw={"points": points, "orders": len(points)},
        )
        if ctx.cache is not None:
            ctx.cache.set(cache_key, score)
        return score

    return FunctionCheck(key, fn, kind=CheckKind.COMPARISON)


__all__ = ["pairwise", "parse_winner"]
