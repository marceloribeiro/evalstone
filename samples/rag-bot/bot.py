"""A tiny retrieval-augmented answerer — no LLM, so the sample runs anywhere.

Retrieval = keyword overlap between the question and each policy paragraph.
"Generation" = return the best paragraph. Deliberately imperfect: some questions
retrieve the wrong paragraph, which is what the eval is there to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).parent / "docs" / "policy.md"
STOP = {"the", "a", "an", "is", "are", "do", "does", "i", "my", "can", "how", "what", "to", "of", "in", "it"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$-]+", text.lower()) if w not in STOP}


def _passages() -> list[str]:
    """Paragraphs of the policy doc, heading lines removed."""
    body = DOCS.read_text(encoding="utf-8")
    out = []
    for block in re.split(r"\n\s*\n", body):
        lines = [ln for ln in block.strip().splitlines() if not ln.startswith("#")]
        if lines:
            out.append(" ".join(lines))
    return out


def retrieve(question: str) -> str:
    q = _words(question)
    best, best_score = "", -1
    for passage in _passages():
        score = len(q & _words(passage))
        if score > best_score:
            best, best_score = passage, score
    return best


def answer(question: str) -> str:
    """The target: question in, answer out."""
    passage = retrieve(question)
    first_sentence = passage.split(". ")[0].rstrip(".")
    return f"{first_sentence}."
