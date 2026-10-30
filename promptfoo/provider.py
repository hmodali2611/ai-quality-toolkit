"""Promptfoo Python provider: sends each test's question to the ShopLite assistant."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiq.evals.assistant import Assistant  # noqa: E402


def call_api(prompt, options, context):
    version = (options.get("config") or {}).get("version", "v1")
    answer = Assistant(version).ask(prompt)
    return {"output": answer.output, "metadata": {"topics": answer.topics, "contexts": answer.contexts}}
