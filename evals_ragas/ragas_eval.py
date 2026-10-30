"""
Ragas evaluation of the ShopLite assistant's retrieval-augmented answers.

    pip install -e ".[ragas]"
    export OPENAI_API_KEY=...
    python evals_ragas/ragas_eval.py --version v1

Metrics:
- Faithfulness: are the answer's claims supported by the retrieved policy?
- ResponseRelevancy: does the answer address the question?
- LLMContextPrecisionWithReference: was the retrieved policy the right one?

Without OPENAI_API_KEY the script builds and prints the Ragas dataset, then exits,
so the data pipeline can still be checked in CI.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiq.evals.assistant import Assistant  # noqa: E402
from aiq.evals.dataset import load_golden  # noqa: E402


def build_samples(version: str) -> list[dict]:
    bot = Assistant(version)
    samples = []
    for case in load_golden():
        if not case.topics:  # out-of-scope questions have no context to score
            continue
        ans = bot.ask(case.question)
        samples.append(
            {
                "user_input": case.question,
                "response": ans.output,
                "retrieved_contexts": ans.contexts,
                "reference": case.reference,
            }
        )
    return samples


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()

    from ragas import EvaluationDataset

    dataset = EvaluationDataset.from_list(build_samples(args.version))
    print(f"Built Ragas dataset with {len(dataset)} samples for assistant {args.version}")

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set: skipping LLM-judged Ragas metrics.")
        return 0

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, ResponseRelevancy

    llm = LangchainLLMWrapper(ChatOpenAI(model=os.environ.get("JUDGE_MODEL", "gpt-4o-mini"), temperature=0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference()],
        llm=llm,
        embeddings=embeddings,
    )
    print(result)
    df = result.to_pandas()
    out = Path("out") / f"ragas-{args.version}.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Per-sample scores -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
