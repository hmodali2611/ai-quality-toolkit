"""Markdown triage report and Jira-ready bug drafts (one per product-defect cluster)."""

from __future__ import annotations

from .classifier import ENVIRONMENT, FLAKY, PRODUCT_DEFECT, TEST_ISSUE, UNKNOWN, Classified, cluster

ACTIONS = {
    PRODUCT_DEFECT: "File a bug",
    TEST_ISSUE: "Fix the test (locator, wait or data)",
    ENVIRONMENT: "Re-run after infra check; notify DevOps",
    FLAKY: "Quarantine and stabilize",
    UNKNOWN: "Investigate manually",
}


def markdown_report(items: list[Classified], total_tests: int) -> str:
    counts = {label: sum(1 for c in items if c.label == label) for label in ACTIONS}
    lines = [
        "# Test failure triage",
        "",
        f"{len(items)} failing of {total_tests} tests in the latest run.",
        "",
        "| Category | Failures | Action |",
        "| --- | --- | --- |",
        *[f"| {label} | {n} | {ACTIONS[label]} |" for label, n in counts.items() if n],
        "",
        "## Root-cause clusters",
        "",
    ]
    for (label, sig), members in cluster(items).items():
        lines += [f"### {label}: `{sig}`", "", f"Why: {members[0].reason}", ""]
        lines += [f"- {m.test}" + (f" (passed in: {', '.join(m.runs_passed)})" if m.runs_passed else "") for m in members]
        lines.append("")
    return "\n".join(lines)


def jira_drafts(items: list[Classified], project_key: str = "QA") -> list[dict]:
    drafts = []
    for (label, sig), members in cluster(items).items():
        if label != PRODUCT_DEFECT:
            continue
        first = members[0]
        description = "\n".join(
            [
                "Found by automated regression. Classified as a product defect by triage rules.",
                "",
                f"Failing tests ({len(members)}):",
                *[f"- {m.test}" for m in members],
                "",
                f"Error: {first.message}",
                f"Evidence: {first.evidence or 'n/a'}",
                f"Failed in runs: {', '.join(first.runs_failed)}",
            ]
        )
        drafts.append(
            {
                "fields": {
                    "project": {"key": project_key},
                    "issuetype": {"name": "Bug"},
                    "summary": f"[Automation] {first.test.split('.')[-1]}: {first.message[:120]}",
                    "description": description,
                    "labels": ["automation", "triage-bot"],
                    "priority": {"name": "High" if len(members) > 1 else "Medium"},
                }
            }
        )
    return drafts
