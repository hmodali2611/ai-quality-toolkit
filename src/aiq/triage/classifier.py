"""
Classify test failures as PRODUCT_DEFECT, TEST_ISSUE, ENVIRONMENT or FLAKY.

Rules come first: they are fast, free and explainable. A model is only asked about
failures the rules cannot place, and its answer is constrained to the same labels.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .junit import Result

PRODUCT_DEFECT = "PRODUCT_DEFECT"
TEST_ISSUE = "TEST_ISSUE"
ENVIRONMENT = "ENVIRONMENT"
FLAKY = "FLAKY"
UNKNOWN = "UNKNOWN"

# (label, pattern, reason) checked in order; first match wins.
RULES: list[tuple[str, re.Pattern, str]] = [
    (ENVIRONMENT, re.compile(r"ECONNREFUSED|CONNECTION_REFUSED|Connection refused|ENOTFOUND|getaddrinfo|\b50[234]\b|Bad Gateway|Service Unavailable|SessionNotCreated|device (is )?offline|no devices? (found|available)", re.I), "infrastructure, network or device farm error"),
    (TEST_ISSUE, re.compile(r"NoSuchElement|StaleElementReference|element (could not be|not) (located|found)|strict mode violation|locator resolved to \d+ elements|ElementNotInteractable", re.I), "locator or element-state problem in the test"),
    (TEST_ISSUE, re.compile(r"TimeoutError|Timeout \d+ms exceeded|TimeoutException|waiting for", re.I), "wait timed out; usually a slow page or a stale locator"),
    (TEST_ISSUE, re.compile(r"test data|fixture|NullPointerException at .*Test|FileNotFound.*\.(json|csv)", re.I), "test code or test data problem"),
    (PRODUCT_DEFECT, re.compile(r"expected[\s:\[\"']+.+?(but (was|found)|received|got)|toHaveText|toEqual|toBe\(|AssertionError|assert .+ ==", re.I), "assertion on product behavior failed"),
    (PRODUCT_DEFECT, re.compile(r"\b(400|409|422|500)\b|Internal Server Error|Unhandled exception|crash", re.I), "the application returned an error"),
]

_NOISE = [
    (re.compile(r"0x[0-9a-f]+", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.I), "<uuid>"),
    (re.compile(r"\d+(\.\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
]


def signature(message: str) -> str:
    """Normalize a failure message so the same root cause groups together across tests and runs."""
    s = message.strip().split("\n")[0]
    for pattern, repl in _NOISE:
        s = pattern.sub(repl, s)
    return s[:160]


@dataclass
class Classified:
    test: str
    label: str
    reason: str
    signature: str
    message: str
    evidence: str = ""
    runs_failed: list[str] = field(default_factory=list)
    runs_passed: list[str] = field(default_factory=list)


def rule_label(result: Result) -> tuple[str, str]:
    text = f"{result.message}\n{result.details}"
    for label, pattern, reason in RULES:
        if pattern.search(text):
            return label, reason
    return UNKNOWN, "no rule matched"


def classify(
    runs: list[list[Result]],
    llm: Callable[[str], str] | None = None,
) -> list[Classified]:
    """
    Classify the failures in the latest run, using earlier runs (oldest first) as history.
    A test that fails, then passes, then fails again is FLAKY. A test that passed and then
    started failing consistently is a new failure and keeps its rule-based label.
    """
    history: dict[str, list[Result]] = defaultdict(list)
    for run in runs:
        for r in run:
            history[r.test].append(r)

    out: list[Classified] = []
    for r in runs[-1]:
        if not r.failed:
            continue
        past = history[r.test]
        failed_in = [h.run for h in past if h.failed]
        passed_in = [h.run for h in past if h.status == "passed"]
        label, reason = rule_label(r)

        if _flips(past):
            label, reason = FLAKY, f"passed and failed alternately across {len(past)} runs; {reason}"
        elif passed_in:
            reason = f"new failure, first seen in {failed_in[0]}; {reason}"
        if label == UNKNOWN and llm is not None:
            label, reason = _ask_llm(llm, r)

        out.append(
            Classified(
                test=r.test,
                label=label,
                reason=reason,
                signature=signature(r.message or r.details),
                message=r.message,
                evidence=r.output[:500],
                runs_failed=failed_in,
                runs_passed=passed_in,
            )
        )
    return out


def _flips(past: list[Result]) -> bool:
    """True when a test passed again after failing: the signature of flakiness, not a regression."""
    seen_fail = False
    for h in past:
        if h.failed:
            seen_fail = True
        elif h.status == "passed" and seen_fail:
            return True
    return False


def _ask_llm(llm: Callable[[str], str], r: Result) -> tuple[str, str]:
    prompt = (
        "Classify this automated test failure. Reply with JSON only: "
        '{"label": "PRODUCT_DEFECT|TEST_ISSUE|ENVIRONMENT", "reason": "<one sentence>"}\n'
        f"Test: {r.test}\nMessage: {r.message}\nDetails: {r.details[:1500]}\nOutput: {r.output[:800]}"
    )
    try:
        raw = llm(prompt)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        if data.get("label") in (PRODUCT_DEFECT, TEST_ISSUE, ENVIRONMENT):
            return data["label"], f"LLM: {data.get('reason', '')}"
    except (ValueError, KeyError):
        pass
    return UNKNOWN, "rules and LLM could not classify"


def cluster(items: list[Classified]) -> dict[tuple[str, str], list[Classified]]:
    """Group failures that share a label and normalized signature: one root cause, one bug."""
    groups: dict[tuple[str, str], list[Classified]] = defaultdict(list)
    for c in items:
        groups[(c.label, c.signature)].append(c)
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))
