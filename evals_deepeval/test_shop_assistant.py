"""
DeepEval suite for the ShopLite assistant.

    deepeval test run evals_deepeval/test_shop_assistant.py      # or: pytest evals_deepeval

- MustIncludeFacts and Groundedness are custom DeepEval metrics built on this repo's
  deterministic scorers, so they run offline and in CI with no API key.
- GEval correctness, Faithfulness and AnswerRelevancy use an LLM judge and run only
  when OPENAI_API_KEY is set.
Set ASSISTANT_VERSION=v2 to watch the suite catch the regressed prompt.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

deepeval = pytest.importorskip("deepeval")
from deepeval import assert_test  # noqa: E402
from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402

from aiq.evals.assistant import Assistant  # noqa: E402
from aiq.evals.dataset import load_golden  # noqa: E402
from aiq.evals.scorers import groundedness, must_include, must_not_include  # noqa: E402

CASES = load_golden()
BOT = Assistant(os.environ.get("ASSISTANT_VERSION", "v1"))
HAS_JUDGE = bool(os.environ.get("OPENAI_API_KEY"))


class MustIncludeFacts(BaseMetric):
    """Every required fact present and no forbidden phrase (e.g. a wrong return window)."""

    def __init__(self, required: list[str], forbidden: list[str], threshold: float = 1.0):
        self.required, self.forbidden, self.threshold = required, forbidden, threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        inc, inc_reason = must_include(test_case.actual_output, self.required)
        exc, exc_reason = must_not_include(test_case.actual_output, self.forbidden)
        self.score = min(inc, exc)
        self.reason = f"{inc_reason}; {exc_reason}"
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Must Include Facts"


class Groundedness(BaseMetric):
    """Share of answer sentences supported by the retrieval context (numbers must match exactly)."""

    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        self.score, self.reason = groundedness(test_case.actual_output, test_case.retrieval_context or [])
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Groundedness"


def judge_metrics():
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval

    correctness = GEval(
        name="Correctness",
        criteria="Is the actual output factually consistent with the expected output and free of invented policy details?",
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
        threshold=0.7,
    )
    return [correctness, FaithfulnessMetric(threshold=0.8), AnswerRelevancyMetric(threshold=0.7)]


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_offline_metrics(case):
    ans = BOT.ask(case.question)
    test_case = LLMTestCase(
        input=case.question,
        actual_output=ans.output,
        expected_output=case.reference,
        retrieval_context=ans.contexts or ["(no matching policy)"],
    )
    assert_test(test_case, [MustIncludeFacts(case.must_include, case.must_not_include), Groundedness()], run_async=False)


@pytest.mark.skipif(not HAS_JUDGE, reason="OPENAI_API_KEY not set: LLM-judge metrics skipped")
@pytest.mark.parametrize("case", [c for c in CASES if c.topics], ids=[c.id for c in CASES if c.topics])
def test_llm_judge_metrics(case):
    ans = BOT.ask(case.question)
    test_case = LLMTestCase(
        input=case.question,
        actual_output=ans.output,
        expected_output=case.reference,
        retrieval_context=ans.contexts,
    )
    assert_test(test_case, judge_metrics())
