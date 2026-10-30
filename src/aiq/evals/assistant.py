"""
The system under test: a small retrieval-augmented support assistant for "ShopLite".

Two versions let the harness demonstrate regression detection:
  v1  baseline prompt: answer only from the retrieved policy, refuse when nothing matches.
  v2  a "make answers shorter" prompt change. With the mock model it simulates what such
      changes often do in practice: answers drop facts and one becomes a hallucination.

ASSISTANT_PROVIDER=mock (default, offline) or openai (uses OPENAI_API_KEY).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

KB_PATH = Path(__file__).resolve().parents[3] / "datasets" / "knowledge_base.json"
REFUSAL = (
    "I don't have information about that. I can only help with ShopLite orders, shipping, "
    "returns, promo codes, warranty and account questions."
)
PROMPTS = {
    "v1": "You are ShopLite's support assistant. Answer ONLY from the policy text provided. "
    f"If the policy does not answer the question, reply exactly: {REFUSAL}",
    "v2": "You are ShopLite's support assistant. Be extremely brief: one short sentence. "
    "Use the policy text provided.",
}
STOP = set("a an the is are am i my me we you your do does can could to of for on in at it be will "
           "how what when where which who why with and or after get have has this that them".split())


def _stem(word: str) -> str:
    w = re.sub(r"(ing|ed|es|s)$", "", word.lower())
    return w[:-1] if len(w) > 3 and w[-1] == w[-2] else w


def content_words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-zA-Z]+", text) if w.lower() not in STOP}


@dataclass
class Answer:
    question: str
    output: str
    contexts: list[str]
    topics: list[str]
    version: str


class Assistant:
    def __init__(self, version: str = "v1", provider: str | None = None):
        if version not in PROMPTS:
            raise ValueError(f"Unknown version {version}; choose from {list(PROMPTS)}")
        self.version = version
        self.provider = (provider or os.environ.get("ASSISTANT_PROVIDER", "mock")).lower()
        self.kb: dict[str, str] = json.loads(KB_PATH.read_text())

    def retrieve(self, question: str, k: int = 1) -> list[tuple[str, str]]:
        q = content_words(question)
        scored = [(len(q & (content_words(text) | {_stem(topic)})), topic, text) for topic, text in self.kb.items()]
        scored = [s for s in sorted(scored, reverse=True) if s[0] > 0]
        return [(topic, text) for _, topic, text in scored[:k]]

    def ask(self, question: str) -> Answer:
        hits = self.retrieve(question)
        topics, contexts = [t for t, _ in hits], [c for _, c in hits]
        if self.provider == "openai":
            output = self._openai(question, contexts)
        else:
            output = self._mock(question, contexts, topics)
        return Answer(question, output, contexts, topics, self.version)

    def _mock(self, question: str, contexts: list[str], topics: list[str]) -> str:
        if not contexts:
            return REFUSAL if self.version == "v1" else "Sure, let me check that for you."
        if self.version == "v1":
            return contexts[0]
        first = re.split(r"(?<=\.)\s+", contexts[0])[0]
        if topics[0] == "returns":
            first = first.replace("30 days", "60 days")  # simulated hallucination
        return first

    def _openai(self, question: str, contexts: list[str]) -> str:
        body = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "temperature": 0,
            "messages": [
                {"role": "system", "content": PROMPTS[self.version]},
                {"role": "user", "content": f"POLICY:\n{chr(10).join(contexts) or '(none)'}\n\nQUESTION: {question}"},
            ],
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json", "authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read())["choices"][0]["message"]["content"].strip()
