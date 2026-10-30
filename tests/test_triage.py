from pathlib import Path

from aiq.triage.classifier import (
    ENVIRONMENT, FLAKY, PRODUCT_DEFECT, TEST_ISSUE, UNKNOWN, classify, cluster, rule_label, signature,
)
from aiq.triage.junit import Result, read_run
from aiq.triage.report import jira_drafts, markdown_report

RUNS = sorted(Path(__file__).resolve().parents[1].joinpath("examples", "runs").glob("run-*.xml"))


def load():
    return [read_run(p) for p in RUNS]


def test_reads_testsuites_and_errors():
    latest = load()[-1]
    assert len(latest) == 7
    wishlist = next(r for r in latest if r.test == "WishlistIOSTest.addToWishlist")
    assert wishlist.failed and "NoSuchElement" in wishlist.message


def test_classifies_each_failure_in_sample_runs():
    labels = {c.test: c.label for c in classify(load())}
    assert labels == {
        "CheckoutTest.applyPromoCode": PRODUCT_DEFECT,
        "CheckoutTest.applyPromoCodeUppercase": PRODUCT_DEFECT,
        "OrderHistoryTest.ordersLoad": FLAKY,  # fail, pass, fail
        "ProfileTest.updateAvatar": ENVIRONMENT,
        "WishlistIOSTest.addToWishlist": TEST_ISSUE,
    }


def test_same_root_cause_clusters_into_one_bug():
    items = classify(load())
    groups = cluster(items)
    defect_groups = [g for (label, _), g in groups.items() if label == PRODUCT_DEFECT]
    assert len(defect_groups) == 1 and len(defect_groups[0]) == 2
    drafts = jira_drafts(items)
    assert len(drafts) == 1
    assert drafts[0]["fields"]["priority"]["name"] == "High"
    assert "PROMO_NOT_FOUND" in drafts[0]["fields"]["description"]


def test_signature_ignores_numbers_and_ids():
    a = signature("Timeout 30000ms exceeded for order 8f14e45f-ceea-4672-9f4b-5a1c3e9e1a2b")
    b = signature("Timeout 15000ms exceeded for order 1c3e9e1a-ceea-4672-9f4b-8f14e45f5a1c")
    assert a == b


def test_unknown_failures_go_to_llm_with_constrained_labels():
    r = Result(run="r1", test="T.weird", status="failed", message="Something odd happened")
    assert rule_label(r)[0] == UNKNOWN
    items = classify([[r]], llm=lambda prompt: '{"label": "ENVIRONMENT", "reason": "disk full on runner"}')
    assert items[0].label == ENVIRONMENT and items[0].reason.startswith("LLM:")
    junk = classify([[r]], llm=lambda prompt: '{"label": "BLAME_DEVOPS"}')
    assert junk[0].label == UNKNOWN


def test_report_lists_counts_and_actions():
    md = markdown_report(classify(load()), 7)
    assert "5 failing of 7 tests" in md
    assert "| PRODUCT_DEFECT | 2 | File a bug |" in md
