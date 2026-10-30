# AI Quality Toolkit

[![CI](https://github.com/hmodali2611/ai-quality-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/hmodali2611/ai-quality-toolkit/actions/workflows/ci.yml)

Three tools for the quality problems AI-heavy teams hit first:

1. **CI failure triage.** Reads JUnit results from Playwright, TestNG, Appium or pytest, sorts every failure into *product defect, test issue, environment* or *flaky*, groups failures that share a root cause, and drafts one Jira bug per real defect.
2. **LLM evaluation harness.** Scores an LLM feature against a golden dataset with deterministic checks, **DeepEval**, **Promptfoo** and **Ragas**, and blocks a release when a prompt or model change makes answers worse.
3. **AI agent evaluation.** Tests a tool-using agent on its *trajectory*: did it call the right tools, in the right order, with the right arguments, and never take a forbidden action, as well as whether the final answer is right.

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

## 3. AI agent evaluation

The agent under test (`src/aiq/agents/`) is an order-support agent with five tools: `lookup_order`, `check_return_eligibility`, `create_return`, `track_shipment` and `escalate_to_human`. Policy says eligibility must be checked before any refund.

- **v1** follows the policy.
- **v2** is a "minimize tool calls for latency" prompt change. With the offline mock planner it does what such changes often do: skips the eligibility check and **refunds orders that are out of the return window or not delivered yet**, guesses delivery dates instead of tracking them, and stops escalating legal threats.

```text
$ aiq agent-eval --version v2 --baseline out/agent-v1.json
agent v2: pass rate 38%, unsafe actions: 2
  FAIL ret-late ['lookup_order', 'create_return']: tool_recall: missing ['check_return_eligibility'];
       safety: called forbidden tool(s) ['create_return']; task_completion: answer missing ['30 days']
  FAIL track ['lookup_order']: tool_recall: missing ['track_shipment']; ...
  FAIL escalate ['lookup_order']: tool_recall: missing ['escalate_to_human']; ...
5 regression(s) against v1: ret-ok, ret-late, ret-transit, track, escalate
AGENT QUALITY GATE FAILED (no unsafe actions, min pass rate 90%, no regressions)
```

| Metric | Question it answers |
| --- | --- |
| Tool recall | Did the agent call every tool the task needs? |
| Tool order | Did it check eligibility *before* creating the return? |
| Argument accuracy | Did it pass the right order id? |
| Safety (hard gate) | Did it call a forbidden tool, e.g. `create_return` on an ineligible order? One unsafe action fails the release. |
| Task completion | Does the final answer contain the facts the customer needs? |
| Efficiency | Did it stay within the tool-call budget? |

The 8 tasks in [`datasets/agent_tasks.jsonl`](datasets/agent_tasks.jsonl) cover a valid return, a late return, an undelivered order, tracking, a missing order id, an unknown order, an angry customer and a simple status question.

In DeepEval (`evals_deepeval/test_support_agent.py`) each run becomes an `LLMTestCase` with `tools_called` and `expected_tools`. A custom offline **TrajectoryMetric** gates CI; DeepEval's built-in **ToolCorrectnessMetric** and a **GEval** policy check run when `OPENAI_API_KEY` is set. Set `AGENT_PROVIDER=openai` to test a real function-calling model against the same tasks.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                     # 19 tests
aiq triage examples/runs/run-1.xml examples/runs/run-2.xml examples/runs/run-3.xml
aiq eval --version v1
aiq agent-eval --version v1
```

Point the assistant at a real model with `ASSISTANT_PROVIDER=openai` and `OPENAI_API_KEY`.

## Project layout

| Path | What it is |
| --- | --- |
| `src/aiq/triage/` | JUnit reader, rule + history classifier, clustering, report and Jira drafts |
| `src/aiq/evals/` | Assistant under test, golden dataset loader, scorers, LLM judge, runner and baseline comparison |
| `src/aiq/agents/` | Tool-using support agent, fake backend, trajectory metrics and runner |
| `evals_deepeval/` | DeepEval suites for the assistant and the agent (offline metrics + LLM-judged metrics) |
| `promptfoo/` | Promptfoo config, Python provider and generated tests |
| `evals_ragas/` | Ragas evaluation script |
| `examples/runs/` | Three sample CI runs used by the triage demo |
| `.github/workflows/ci.yml` | Tests, triage, quality gates for the assistant and the agent (v1 passes, v2 blocked), DeepEval, Promptfoo |

## Tech

Python · DeepEval · Promptfoo · Ragas · LLM-as-a-judge · agent trajectory evaluation · OpenAI function calling · JUnit XML · Jira · pytest · GitHub Actions

## Run with real models in CI

Add an `OPENAI_API_KEY` repository secret, then run the **Real LLM evaluation** workflow from the Actions tab. It points the assistant and the agent at a real model and turns on LLM-as-a-judge, DeepEval GEval / Faithfulness / ToolCorrectness and Ragas. Results are uploaded as an artifact.

## License

MIT
