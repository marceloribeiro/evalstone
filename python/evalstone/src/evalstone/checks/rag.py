"""RAG checks — the three questions a retrieval-augmented answer can fail.

Each is a ``judge`` with a narrow rubric. The sample input is expected to carry
the question and the retrieved context (``{"question": …, "context": …}`` by
default; the field names are configurable). Measuring them separately tells
you whether to fix the retriever or the prompt (Evals 101, chapter 4).
"""

from __future__ import annotations

from evalstone.checks.judge import JudgeCheck, judge

_FAITHFULNESS = """You are checking FAITHFULNESS of an answer to its source material.
The INPUT contains the field `{context}` — the only material the answer may rely on.
Grade whether every factual claim in the ANSWER is supported by `{context}`.
5 = every claim supported · 4 = one minor unsupported detail · 3 = one substantive unsupported
claim · 2 = several unsupported claims · 1 = the answer contradicts the context or is fabricated.
Ignore style, tone and whether the answer is complete; judge only support by the context."""

_CONTEXT_RELEVANCE = """You are checking CONTEXT RELEVANCE for a retrieval system.
The INPUT contains `{question}` (what was asked) and `{context}` (what retrieval returned).
Grade whether `{context}` contains the information needed to answer `{question}`.
5 = fully answers it · 4 = answers it with minor gaps · 3 = partially relevant · 2 = tangential ·
1 = unrelated. Ignore the ANSWER entirely; judge only the retrieved context."""

_ANSWER_RELEVANCE = """You are checking ANSWER RELEVANCE.
The INPUT contains `{question}`. Grade whether the ANSWER actually addresses that question.
5 = directly and completely addresses it · 4 = addresses it with a minor omission ·
3 = partially addresses it · 2 = mostly off-topic · 1 = does not address it.
Ignore factual accuracy (another check covers that); judge only whether the question was
answered."""


def faithfulness(
    key: str = "faithfulness",
    *,
    context: str = "context",
    model: str | None = None,
    threshold: float | None = None,
) -> JudgeCheck:
    """Every claim in the answer is supported by ``sample.input[context]``."""
    return judge(key, _FAITHFULNESS.format(context=context), model=model, threshold=threshold)


def context_relevance(
    key: str = "context_relevance",
    *,
    question: str = "question",
    context: str = "context",
    model: str | None = None,
    threshold: float | None = None,
) -> JudgeCheck:
    """The retrieved ``context`` can answer the ``question``."""
    rubric = _CONTEXT_RELEVANCE.format(question=question, context=context)
    return judge(key, rubric, model=model, threshold=threshold)


def answer_relevance(
    key: str = "answer_relevance",
    *,
    question: str = "question",
    model: str | None = None,
    threshold: float | None = None,
) -> JudgeCheck:
    """The answer addresses the ``question``."""
    rubric = _ANSWER_RELEVANCE.format(question=question)
    return judge(key, rubric, model=model, threshold=threshold)


__all__ = ["answer_relevance", "context_relevance", "faithfulness"]
