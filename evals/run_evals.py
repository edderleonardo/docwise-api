"""
RAG evaluation harness.

Runs the golden dataset (evals/golden/dataset.json) through the REAL pipeline —
ingestion, query expansion, pgvector retrieval, and Gemini generation, no mocks —
and scores every answer with DeepEval's LLM-as-judge metrics:

  - Faithfulness:      does the answer invent facts outside the retrieved context?
  - Answer Relevancy:  does the answer actually address the question?

This is NOT part of the pytest suite on purpose: evals are slow, cost real API
calls, and are non-deterministic (the judge is an LLM). The pytest suite checks
that the code works; this harness measures how well the system answers.

The Gemini free tier allows only 5 requests/min on flash models, so every call
(generation and judge) is paced ~13s apart. A full 13-question run takes
~25 minutes; use --limit for a quick smoke run.

Usage:
    uv run --group evals python evals/run_evals.py            # full dataset
    uv run --group evals python evals/run_evals.py --limit 3  # quick smoke run

Requires: Postgres running (docker compose up -d) and GEMINI_API_KEY in .env.
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase

from app.config import settings
from app.core.ingestion import chunk_and_embed
from app.core.llm import expand_query, stream_response
from app.core.retrieval import get_relevant_chunks
from app.db.database import AsyncSessionLocal
from app.db.models import Chunk, Session

GOLDEN_DIR = Path(__file__).parent / "golden"

# Ideally the judge is a stronger model than the one being judged, but the
# Gemini free tier only serves flash models (pro returns 429 with limit 0).
# Same-model judging has a self-preference bias — treat absolute scores with
# skepticism and trust the *relative* comparison between configs. With billing
# enabled, override: EVAL_JUDGE_MODEL=gemini-3.1-pro-preview
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "gemini-3.5-flash")

# Free tier: 5 requests/min → one request every ~13s stays under the limit.
# With billing enabled set EVAL_REQUEST_INTERVAL=0.
REQUEST_INTERVAL = float(os.environ.get("EVAL_REQUEST_INTERVAL", "13"))

THRESHOLD = 0.7

_last_request = 0.0


def _pace_sync() -> None:
    """Block until a free-tier request slot is available (5 RPM)."""
    global _last_request
    wait = _last_request + REQUEST_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


async def _pace() -> None:
    global _last_request
    wait = _last_request + REQUEST_INTERVAL - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request = time.monotonic()


class ThrottledGeminiModel(GeminiModel):
    """Judge model that respects the free-tier rate limit on every call."""

    def generate(self, *args, **kwargs):
        _pace_sync()
        return super().generate(*args, **kwargs)

    async def a_generate(self, *args, **kwargs):
        await _pace()
        return await super().a_generate(*args, **kwargs)


async def ingest_reference(db) -> Session:
    """Push the reference PDF through the real ingestion pipeline."""
    pdf_bytes = (GOLDEN_DIR / "reference.pdf").read_bytes()
    records = chunk_and_embed(pdf_bytes, "reference.pdf")

    session = Session(filename="eval-reference.pdf", status="ready")
    db.add(session)
    await db.flush()
    for record in records:
        db.add(Chunk(session_id=session.id, **record))
    await db.commit()

    print(f"Ingested reference.pdf → {len(records)} chunks (session {session.id})")
    return session


async def answer_question(db, session_id, question: str) -> tuple[str, list[str]]:
    """Mirror of chat_service.generate_chat_response, minus session bookkeeping."""
    await _pace()
    search_query = await expand_query(question)
    chunks = await get_relevant_chunks(session_id, search_query, db)
    await _pace()
    answer = "".join([token async for token in stream_response(question, chunks)])
    return answer, chunks


async def build_test_cases(limit: int | None) -> list[LLMTestCase]:
    dataset = json.loads((GOLDEN_DIR / "dataset.json").read_text())
    if limit:
        dataset = dataset[:limit]

    test_cases = []
    async with AsyncSessionLocal() as db:
        session = await ingest_reference(db)
        try:
            for i, item in enumerate(dataset, start=1):
                answer, chunks = await answer_question(
                    db, session.id, item["question"]
                )
                test_cases.append(
                    LLMTestCase(
                        input=item["question"],
                        actual_output=answer,
                        retrieval_context=chunks,
                        expected_output=item["expected_output"],
                        additional_metadata={"category": item["category"]},
                    )
                )
                print(f"  [{i}/{len(dataset)}] {item['question'][:60]}")
        finally:
            await db.delete(session)
            await db.commit()

    return test_cases


def score_test_cases(test_cases: list[LLMTestCase]) -> list[dict]:
    """
    Sequential evaluation (async_mode=False): DeepEval's evaluate() fires judge
    calls concurrently, which instantly trips the 5 RPM free-tier limit.
    """
    judge = ThrottledGeminiModel(
        JUDGE_MODEL, api_key=settings.gemini_api_key, temperature=0
    )
    metrics = [
        FaithfulnessMetric(
            threshold=THRESHOLD, model=judge, include_reason=True, async_mode=False
        ),
        AnswerRelevancyMetric(
            threshold=THRESHOLD, model=judge, include_reason=True, async_mode=False
        ),
    ]

    results = []
    for i, tc in enumerate(test_cases, start=1):
        row = {"question": tc.input, "category": tc.additional_metadata["category"]}
        for metric in metrics:
            name = metric.__class__.__name__.removesuffix("Metric")
            try:
                metric.measure(tc)
                row[name] = metric.score
                if metric.score < THRESHOLD:
                    row[f"{name}_reason"] = metric.reason
            except Exception as exc:  # keep scoring the rest on judge errors
                row[name] = None
                row[f"{name}_reason"] = f"judge error: {exc}"
        print(f"  [{i}/{len(test_cases)}] scored: {tc.input[:50]}")
        results.append(row)
    return results


def print_report(results: list[dict]) -> None:
    metric_names = ["Faithfulness", "AnswerRelevancy"]

    print("\n" + "=" * 78)
    print(f"{'Question':<48} {'Category':<12} " + " ".join(f"{m[:5]:>6}" for m in metric_names))
    print("-" * 78)
    for row in results:
        scores = " ".join(
            f"{row[m]:>6.2f}" if row.get(m) is not None else "   n/a"
            for m in metric_names
        )
        print(f"{row['question'][:47]:<48} {row['category']:<12} {scores}")

    print("-" * 78)
    for m in metric_names:
        scores = [r[m] for r in results if r.get(m) is not None]
        if scores:
            print(f"{m}: avg={sum(scores) / len(scores):.3f}  "
                  f"min={min(scores):.2f}  passing={sum(s >= THRESHOLD for s in scores)}/{len(scores)}")

    failures = [r for r in results if any(f"{m}_reason" in r for m in metric_names)]
    if failures:
        print("\nBelow threshold / errors:")
        for row in failures:
            print(f"\n  Q: {row['question']}")
            for m in metric_names:
                if f"{m}_reason" in row:
                    print(f"  {m}: {row.get(m)} — {row[f'{m}_reason']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=None, help="only run the first N questions"
    )
    args = parser.parse_args()

    print("Config under evaluation:")
    print(f"  chunk_size={settings.chunk_size}  chunk_overlap={settings.chunk_overlap}")
    print(f"  top_k_results={settings.top_k_results}")
    print(f"  generation model={settings.gemini_model}  judge={JUDGE_MODEL}")
    print(f"  request interval={REQUEST_INTERVAL}s (free-tier pacing)")
    print()

    print("Generating answers through the RAG pipeline:")
    test_cases = asyncio.run(build_test_cases(args.limit))

    print("\nScoring with the judge:")
    results = score_test_cases(test_cases)

    print_report(results)


if __name__ == "__main__":
    main()
