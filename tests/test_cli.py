import json
from pathlib import Path

from aiq.cli import main

RUNS = sorted(str(p) for p in Path(__file__).resolve().parents[1].joinpath("examples", "runs").glob("run-*.xml"))


def test_triage_writes_report_and_drafts(tmp_path):
    assert main(["triage", *RUNS, "--out", str(tmp_path)]) == 0
    assert "Root-cause clusters" in (tmp_path / "triage.md").read_text()
    assert len(json.loads((tmp_path / "jira-drafts.json").read_text())) == 1


def test_quality_gate_passes_baseline_and_blocks_regression(tmp_path):
    baseline = tmp_path / "v1.json"
    assert main(["eval", "--version", "v1", "--out", str(baseline), "--no-judge"]) == 0
    assert main(["eval", "--version", "v2", "--baseline", str(baseline), "--no-judge"]) == 1


def test_promptfoo_export(tmp_path):
    out = tmp_path / "tests.yaml"
    assert main(["promptfoo-tests", "--out", str(out)]) == 0
    text = out.read_text()
    assert text.count("- description:") == 10 and "llm-rubric" not in text
    assert main(["promptfoo-tests", "--out", str(out), "--llm-rubric"]) == 0
    assert "llm-rubric" in out.read_text()
