from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[3] / "datasets" / "golden.jsonl"


@dataclass
class GoldenCase:
    id: str
    category: str
    question: str
    topics: list[str]
    must_include: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    reference: str = ""


def load_golden(path: Path = GOLDEN) -> list[GoldenCase]:
    return [GoldenCase(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
