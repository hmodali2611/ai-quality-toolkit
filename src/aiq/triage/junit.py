"""Read JUnit XML (Playwright, TestNG, Surefire, pytest) into plain records."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    run: str
    test: str
    status: str  # passed | failed | skipped
    message: str = ""
    details: str = ""
    output: str = ""
    duration: float = 0.0

    @property
    def failed(self) -> bool:
        return self.status == "failed"


def read_run(path: Path) -> list[Result]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    results = []
    for suite in suites:
        for tc in suite.findall("testcase"):
            problem = tc.find("failure")
            if problem is None:
                problem = tc.find("error")
            status = "failed" if problem is not None else "skipped" if tc.find("skipped") is not None else "passed"
            name = tc.get("name", "")
            classname = tc.get("classname")
            results.append(
                Result(
                    run=path.stem,
                    test=f"{classname}.{name}" if classname else name,
                    status=status,
                    message=(problem.get("message") or (problem.text or "").strip().split("\n")[0]) if problem is not None else "",
                    details=(problem.text or "").strip() if problem is not None else "",
                    output=(tc.findtext("system-out") or "").strip(),
                    duration=float(tc.get("time", 0) or 0),
                )
            )
    return results
