"""
Deterministic scorers: fast, free, and stable enough to gate a CI pipeline.
LLM-as-a-judge (judge.py, DeepEval, Promptfoo llm-rubric, Ragas) adds semantic checks on top.
"""

from __future__ import annotations

import re

from .assistant import REFUSAL, content_words


def must_include(output: str, required: list[str]) -> tuple[float, str]:
    missing = [r for r in required if r.lower() not in output.lower()]
    score = 1.0 if not required else (len(required) - len(missing)) / len(required)
    return score, f"missing {missing}" if missing else "all required facts present"


def must_not_include(output: str, forbidden: list[str]) -> tuple[float, str]:
    found = [f for f in forbidden if f.lower() in output.lower()]
    return (0.0, f"contains forbidden {found}") if found else (1.0, "no forbidden content")


def groundedness(output: str, contexts: list[str], threshold: float = 0.6) -> tuple[float, str]:
    """
    Share of answer sentences supported by the retrieved context: a sentence counts as
    supported when most of its content words, and every number in it, appear in the context.
    A refusal is grounded by definition.
    """
    if output.strip() == REFUSAL:
        return 1.0, "refusal"
    context = " ".join(contexts)
    ctx_words, ctx_numbers = content_words(context), set(re.findall(r"\d+(?:[.-]\d+)?", context))
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", output.strip()) if s]
    unsupported = []
    for s in sentences:
        words = content_words(s)
        numbers = set(re.findall(r"\d+(?:[.-]\d+)?", s))
        overlap = len(words & ctx_words) / len(words) if words else 1.0
        if overlap < threshold or not numbers <= ctx_numbers:
            unsupported.append(s)
    score = 1 - len(unsupported) / len(sentences) if sentences else 0.0
    return score, f"unsupported: {unsupported}" if unsupported else "every sentence supported by context"
