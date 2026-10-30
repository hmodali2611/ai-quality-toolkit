"""
aiq triage examples/runs/run-1.xml examples/runs/run-2.xml examples/runs/run-3.xml --out out/triage
aiq eval --version v1 --out out/v1.json
aiq eval --version v2 --baseline out/v1.json --min-pass-rate 0.9      # exits 1 on regression
aiq promptfoo-tests --out promptfoo/tests.yaml [--llm-rubric]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evals.dataset import load_golden
from .evals.runner import compare, evaluate, summary
from .triage.classifier import classify
from .triage.junit import read_run
from .triage.report import jira_drafts, markdown_report


def cmd_triage(args) -> int:
    runs = [read_run(Path(p)) for p in args.reports]  # oldest first
    items = classify(runs)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "triage.md").write_text(markdown_report(items, len(runs[-1])))
    drafts = jira_drafts(items, args.jira_project)
    (args.out / "jira-drafts.json").write_text(json.dumps(drafts, indent=2))
    for c in items:
        print(f"{c.label:<15} {c.test}")
    print(f"{len(items)} failures triaged, {len(drafts)} bug draft(s) -> {args.out}")
    return 0


def cmd_eval(args) -> int:
    run = evaluate(args.version, use_judge=args.judge)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(run, indent=2))
    regressions = compare(json.loads(args.baseline.read_text()), run) if args.baseline else None
    print(summary(run, regressions))
    failed_gate = run["pass_rate"] < args.min_pass_rate or bool(regressions)
    if failed_gate:
        print(f"QUALITY GATE FAILED (min pass rate {args.min_pass_rate:.0%}, no regressions allowed)")
    return 1 if failed_gate else 0


def cmd_promptfoo(args) -> int:
    """Export the golden set as Promptfoo tests so both tools evaluate the same cases."""
    lines = ["# Generated from datasets/golden.jsonl by `aiq promptfoo-tests`. Do not edit by hand.", ""]
    for c in load_golden():
        lines += [f"- description: \"{c.id} ({c.category})\"", "  vars:", f"    question: {json.dumps(c.question)}", "  assert:"]
        if c.must_include:
            lines += ["    - type: icontains-all", f"      value: {json.dumps(c.must_include)}"]
        for bad in c.must_not_include:
            lines += ["    - type: not-icontains", f"      value: {json.dumps(bad)}"]
        if args.llm_rubric:
            lines += ["    - type: llm-rubric", f"      value: {json.dumps('Consistent with: ' + c.reference)}", "      metric: correctness"]
    args.out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aiq", description="AI quality toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("triage", help="Classify failures from JUnit reports (oldest first)")
    t.add_argument("reports", nargs="+")
    t.add_argument("--out", type=Path, default=Path("out/triage"))
    t.add_argument("--jira-project", default="QA")
    t.set_defaults(fn=cmd_triage)

    e = sub.add_parser("eval", help="Evaluate the assistant on the golden dataset")
    e.add_argument("--version", default="v1")
    e.add_argument("--out", type=Path)
    e.add_argument("--baseline", type=Path)
    e.add_argument("--min-pass-rate", type=float, default=0.9)
    e.add_argument("--judge", action=argparse.BooleanOptionalAction, default=None, help="LLM-as-a-judge (default: on when OPENAI_API_KEY is set)")
    e.set_defaults(fn=cmd_eval)

    p = sub.add_parser("promptfoo-tests", help="Export golden cases as Promptfoo tests")
    p.add_argument("--out", type=Path, default=Path("promptfoo/tests.yaml"))
    p.add_argument("--llm-rubric", action="store_true", help="Add an LLM-graded correctness check (needs OPENAI_API_KEY)")
    p.set_defaults(fn=cmd_promptfoo)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
