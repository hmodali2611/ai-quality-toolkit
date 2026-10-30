"""Run the golden dataset against an assistant version, score it, and compare against a baseline."""

from __future__ import annotations

import time
from collections import defaultdict

from . import judge
from .assistant import Assistant
from .dataset import GoldenCase, load_golden
from .scorers import groundedness, must_include, must_not_include

GROUNDED_MIN = 0.8


def evaluate(version: str = "v1", cases: list[GoldenCase] | None = None, use_judge: bool | None = None) -> dict:
    cases = cases or load_golden()
    use_judge = judge.available() if use_judge is None else use_judge
    bot = Assistant(version)
    results = []
    for case in cases:
        started = time.perf_counter()
        ans = bot.ask(case.question)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        scores = {
            "retrieval": (1.0, "correct policy retrieved") if ans.topics == case.topics else (0.0, f"retrieved {ans.topics}, expected {case.topics}"),
            "must_include": must_include(ans.output, case.must_include),
            "must_not_include": must_not_include(ans.output, case.must_not_include),
            "groundedness": groundedness(ans.output, ans.contexts),
        }
        if use_judge:
            scores["llm_judge"] = judge.judge(case.question, ans.output, case.reference)
        passed = (
            scores["retrieval"][0] == 1
            and scores["must_include"][0] == 1
            and scores["must_not_include"][0] == 1
            and scores["groundedness"][0] >= GROUNDED_MIN
            and (not use_judge or scores["llm_judge"][0] >= 0.5)
        )
        results.append(
            {
                "id": case.id,
                "category": case.category,
                "question": case.question,
                "output": ans.output,
                "passed": passed,
                "latency_ms": latency_ms,
                "scores": {k: {"score": round(v[0], 3), "reason": v[1]} for k, v in scores.items()},
            }
        )

    by_cat: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r["passed"])
    return {
        "version": version,
        "judge": use_judge,
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3),
        "by_category": {c: round(sum(v) / len(v), 3) for c, v in sorted(by_cat.items())},
        "results": results,
    }


def compare(baseline: dict, candidate: dict) -> list[dict]:
    """Cases that passed in the baseline and fail in the candidate."""
    before = {r["id"]: r for r in baseline["results"]}
    regressions = []
    for r in candidate["results"]:
        b = before.get(r["id"])
        if b and b["passed"] and not r["passed"]:
            failing = {k: v["reason"] for k, v in r["scores"].items() if v["score"] < 1}
            regressions.append({"id": r["id"], "question": r["question"], "output": r["output"], "why": failing})
    return regressions


def summary(run: dict, regressions: list[dict] | None = None) -> str:
    lines = [f"version {run['version']}: pass rate {run['pass_rate']:.0%} (LLM judge {'on' if run['judge'] else 'off'})"]
    lines += [f"  {cat:<13} {rate:.0%}" for cat, rate in run["by_category"].items()]
    for r in run["results"]:
        if not r["passed"]:
            bad = "; ".join(f"{k}: {v['reason']}" for k, v in r["scores"].items() if v["score"] < 1)
            lines.append(f"  FAIL {r['id']}: {bad}")
    if regressions is not None:
        lines.append(f"{len(regressions)} regression(s) against baseline")
        lines += [f"  REGRESSED {x['id']}: {x['question']}" for x in regressions]
    return "\n".join(lines)
