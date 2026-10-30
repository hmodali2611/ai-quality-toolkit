# AI Quality Toolkit

Two tools for the two quality problems AI-heavy teams hit first:

1. **CI failure triage.** Reads JUnit results from Playwright, TestNG, Appium or pytest, sorts every failure into *product defect, test issue, environment* or *flaky*, groups failures that share a root cause, and drafts one Jira bug per real defect.
2. **LLM evaluation harness.** Scores an LLM feature against a golden dataset with deterministic checks, **DeepEval**, **Promptfoo** and **Ragas**, and blocks a release when a prompt or model change makes answers worse.

## 1. Failure triage

```text
$ aiq triage examples/runs/run-1.xml examples/runs/run-2.xml examples/runs/run-3.xml
PRODUCT_DEFECT  CheckoutTest.applyPromoCode
PRODUCT_DEFECT  CheckoutTest.applyPromoCodeUppercase
FLAKY           OrderHistoryTest.ordersLoad
ENVIRONMENT     ProfileTest.updateAvatar
TEST_ISSUE      WishlistIOSTest.addToWishlist
5 failures triaged, 1 bug draft(s)
```

How it decides:

| Step | Detail |
| --- | --- |
| Rules first | Regex signatures for infra errors (connection refused, 502/503, device offline), test problems (NoSuchElement, stale element, timeouts) and product failures (assertion mismatches, 4xx/5xx from the app). Fast, free, explainable. |
| History | Runs are read oldest first. A test that fails, passes, then fails again is **flaky**. One that passed and now fails every time is a **new failure** and keeps its label. |
| Clustering | Messages are normalized (numbers, UUIDs, hex removed) so the two promo-code failures become **one** bug, not two. |
| LLM fallback | Only failures no rule can place go to a model, and its answer must be one of the allowed labels; anything else stays `UNKNOWN`. |

Output: [`examples/sample-output/triage.md`](examples/sample-output/triage.md) and [`jira-drafts.json`](examples/sample-output/jira-drafts.json).

## 2. LLM evaluation harness

The system under test is a small retrieval-augmented support assistant (`src/aiq/evals/assistant.py`) with two prompt versions:

- **v1** answers only from the retrieved policy and refuses out-of-scope questions.
- **v2** is a "be brief" prompt change. With the offline mock model it simulates what such changes often do: answers drop facts, one states a 60-day return window that does not exist, and out-of-scope questions stop being refused.

```text
$ aiq eval --version v1 --out out/v1.json
version v1: pass rate 100%

$ aiq eval --version v2 --baseline out/v1.json
version v2: pass rate 20%
  FAIL ret-01: must_include: missing ['30 days']; must_not_include: contains forbidden ['60 days'];
               groundedness: unsupported: ['Items can be returned within 60 days of delivery ...']
  ...
8 regression(s) against baseline
QUALITY GATE FAILED (min pass rate 90%, no regressions allowed)        # exit code 1
```

### What is measured

| Check | Tool | Needs an API key? |
| --- | --- | --- |
| Retrieval picked the right policy | `aiq eval` | No |
| Required facts present, forbidden claims absent | `aiq eval`, DeepEval custom metric, Promptfoo `icontains-all` / `not-icontains` | No |
| Groundedness: every sentence and every number supported by context | `aiq eval`, DeepEval custom metric | No |
| Correctness vs. reference (LLM-as-a-judge) | `aiq eval --judge`, DeepEval **GEval**, Promptfoo **llm-rubric** | Yes |
| Faithfulness, answer relevancy | DeepEval **FaithfulnessMetric**, **AnswerRelevancyMetric**; **Ragas** Faithfulness, ResponseRelevancy | Yes |
| Context precision | **Ragas** LLMContextPrecisionWithReference | Yes |

The deterministic checks gate CI on every commit at no cost. LLM-judged metrics add semantic depth when `OPENAI_API_KEY` is set.

### One golden dataset, three frameworks

[`datasets/golden.jsonl`](datasets/golden.jsonl) holds 10 cases across returns, shipping, promo codes, warranty, account safety and out-of-scope questions. Every framework reads it:

```bash
# DeepEval: custom offline metrics + GEval / Faithfulness / AnswerRelevancy with a key
pip install -e ".[deepeval]"
deepeval test run evals_deepeval/test_shop_assistant.py
ASSISTANT_VERSION=v2 deepeval test run evals_deepeval/test_shop_assistant.py   # 8 failures

# Promptfoo: side-by-side v1 vs v2 (tests generated from the golden set)
aiq promptfoo-tests            # add --llm-rubric for LLM-graded correctness
cd promptfoo && npx promptfoo@latest eval && npx promptfoo@latest view

# Ragas: faithfulness, relevancy and context precision for the RAG answers
pip install -e ".[ragas]" && export OPENAI_API_KEY=...
python evals_ragas/ragas_eval.py --version v1
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                     # 13 tests
aiq triage examples/runs/run-1.xml examples/runs/run-2.xml examples/runs/run-3.xml
aiq eval --version v1
```

Point the assistant at a real model with `ASSISTANT_PROVIDER=openai` and `OPENAI_API_KEY`.

## Project layout

| Path | What it is |
| --- | --- |
| `src/aiq/triage/` | JUnit reader, rule + history classifier, clustering, report and Jira drafts |
| `src/aiq/evals/` | Assistant under test, golden dataset loader, scorers, LLM judge, runner and baseline comparison |
| `evals_deepeval/` | DeepEval suite (custom offline metrics + LLM-judged metrics) |
| `promptfoo/` | Promptfoo config, Python provider and generated tests |
| `evals_ragas/` | Ragas evaluation script |
| `examples/runs/` | Three sample CI runs used by the triage demo |
| `.github/workflows/ci.yml` | Tests, triage, quality gate (v1 passes, v2 blocked), DeepEval, Promptfoo |

## Tech

Python · DeepEval · Promptfoo · Ragas · LLM-as-a-judge · JUnit XML · Jira · pytest · GitHub Actions

## License

MIT
