from aiq.evals.assistant import REFUSAL, Assistant
from aiq.evals.dataset import load_golden
from aiq.evals.runner import compare, evaluate
from aiq.evals.scorers import groundedness, must_include, must_not_include


def test_golden_dataset_loads():
    cases = load_golden()
    assert len(cases) == 10
    assert {c.category for c in cases} >= {"returns", "shipping", "promo", "safety", "out_of_scope"}


def test_retrieval_picks_the_right_policy():
    bot = Assistant("v1")
    for case in load_golden():
        assert [t for t, _ in bot.retrieve(case.question)] == case.topics, case.id


def test_scorers():
    assert must_include("Returns within 30 days.", ["30 days"])[0] == 1
    assert must_include("Returns allowed.", ["30 days", "refund"])[0] == 0
    assert must_not_include("within 60 days", ["60 days"])[0] == 0
    ctx = ["Items can be returned within 30 days of delivery."]
    assert groundedness("Items can be returned within 30 days of delivery.", ctx)[0] == 1
    assert groundedness("Items can be returned within 60 days of delivery.", ctx)[0] == 0  # wrong number
    assert groundedness("We also offer free gift wrapping worldwide.", ctx)[0] == 0  # invented
    assert groundedness(REFUSAL, [])[0] == 1


def test_baseline_passes_and_regressed_prompt_is_caught():
    v1, v2 = evaluate("v1", use_judge=False), evaluate("v2", use_judge=False)
    assert v1["pass_rate"] == 1.0
    assert v2["pass_rate"] < 0.5
    regressions = {r["id"]: r for r in compare(v1, v2)}
    assert "ret-01" in regressions
    assert "60 days" in regressions["ret-01"]["why"]["must_not_include"]
    assert "oos-01" in regressions  # v2 stopped refusing out-of-scope questions
