"""Run the agent task set, score each trajectory, and compare versions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .agent import SupportAgent
from .metrics import argument_accuracy, efficiency, safety, task_completion, tool_order, tool_recall

TASKS = Path(__file__).resolve().parents[3] / "datasets" / "agent_tasks.jsonl"
# Safety is a hard gate: a single forbidden action fails the task regardless of other scores.
REQUIRED = ("tool_recall", "tool_order", "arguments", "safety", "task_completion", "efficiency")


@dataclass
class AgentTask:
    id: str
    task: str
    expected_tools: list[str]
    expected_args: dict
    forbidden_tools: list[str]
    must_include: list[str]
    max_tool_calls: int


def load_tasks(path: Path = TASKS) -> list[AgentTask]:
    return [AgentTask(**json.loads(l)) for l in path.read_text().splitlines() if l.strip()]


def evaluate_agent(version: str = "v1", tasks: list[AgentTask] | None = None) -> dict:
    tasks = tasks or load_tasks()
    agent = SupportAgent(version)
    results = []
    for t in tasks:
        run = agent.run(t.task)
        called = [c["name"] for c in run.tool_calls]
        scores = {
            "tool_recall": tool_recall(called, t.expected_tools),
            "tool_order": tool_order(called, t.expected_tools),
            "arguments": argument_accuracy(run.tool_calls, t.expected_args),
            "safety": safety(called, t.forbidden_tools),
            "task_completion": task_completion(run.final_answer, t.must_include),
            "efficiency": efficiency(called, t.max_tool_calls),
        }
        results.append(
            {
                "id": t.id,
                "task": t.task,
                "tools_called": called,
                "answer": run.final_answer,
                "passed": all(scores[k][0] == 1 for k in REQUIRED),
                "unsafe": scores["safety"][0] < 1,
                "scores": {k: {"score": round(v[0], 3), "reason": v[1]} for k, v in scores.items()},
            }
        )
    n = len(results)
    metric_avgs = {k: round(sum(r["scores"][k]["score"] for r in results) / n, 3) for k in REQUIRED}
    return {
        "version": version,
        "pass_rate": round(sum(r["passed"] for r in results) / n, 3),
        "unsafe_actions": sum(r["unsafe"] for r in results),
        "metrics": metric_avgs,
        "results": results,
    }


def summary(run: dict, baseline: dict | None = None) -> str:
    lines = [f"agent {run['version']}: pass rate {run['pass_rate']:.0%}, unsafe actions: {run['unsafe_actions']}"]
    lines += [f"  {k:<16} {v:.0%}" for k, v in run["metrics"].items()]
    for r in run["results"]:
        if not r["passed"]:
            bad = "; ".join(f"{k}: {v['reason']}" for k, v in r["scores"].items() if v["score"] < 1)
            lines.append(f"  FAIL {r['id']} {r['tools_called']}: {bad}")
    if baseline:
        before = {r["id"]: r["passed"] for r in baseline["results"]}
        reg = [r["id"] for r in run["results"] if before.get(r["id"]) and not r["passed"]]
        lines.append(f"{len(reg)} regression(s) against {baseline['version']}: {', '.join(reg) or 'none'}")
    return "\n".join(lines)
