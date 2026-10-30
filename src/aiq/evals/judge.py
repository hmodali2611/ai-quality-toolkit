"""Optional LLM-as-a-judge scorer (OpenAI). Skipped automatically when OPENAI_API_KEY is not set."""

from __future__ import annotations

import json
import os
import urllib.request

RUBRIC = """You grade a customer-support answer against a reference answer.
Score 1.0 if the answer is correct and complete for the question, 0.5 if partly correct, 0.0 if wrong,
misleading or invented. Reply with JSON only: {"score": <0|0.5|1>, "reason": "<one sentence>"}"""


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def judge(question: str, answer: str, reference: str) -> tuple[float, str]:
    body = {
        "model": os.environ.get("JUDGE_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": f"QUESTION: {question}\nREFERENCE: {reference}\nANSWER: {answer}"},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.loads(json.loads(res.read())["choices"][0]["message"]["content"])
    return float(data["score"]), data.get("reason", "")
