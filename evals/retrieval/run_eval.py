"""Run the retriever eval: Contextual Recall and Contextual Precision over the retrieval goldens.

Run from the repo root:  uv run --project backend --group evals python evals/retrieval/run_eval.py

Retrieves chunks for each golden with the app's QdrantRetriever and Settings, has the judge model
score them, and writes three files to evals/results/retrieval/: DeepEval's test_run_*.json, with
every verdict and reason; a summary_*.json with the scores by question and category and the
settings the run used; and a report_*.md that shows the same results for reading. See ADR 0006.
"""

# ruff: noqa: E402  (the environment must be set before deepeval is imported)

import argparse
import asyncio
import hashlib
import inspect
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

# DeepEval copies the working directory's .env into the process environment on import, which
# would switch on LangSmith tracing. Settings reads .env itself, so turn that off.
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")

from deepeval import evaluate
from deepeval.dataset import Golden
from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig
from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import QdrantClient

from hr_assist.answering.adapters import QdrantRetriever
from hr_assist.ingestion import STRATEGIES
from hr_assist.settings import REPO_ROOT, REPO_ROOT_ENV_FILE, Settings

GOLDENS = Path(__file__).resolve().parent / "goldens_v1.jsonl"
RESULTS = REPO_ROOT / "evals" / "results" / "retrieval"
CONCURRENT_RETRIEVALS = 8
# Characters of each chunk's body shown in the report; the test_run file has the full text.
REPORT_EXCERPT_CHARS = 300


class EvalSettings(BaseSettings):
    """Eval-only settings. The API never uses the judge, so it isn't in the app's Settings."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    eval_judge_model: str = "gpt-6-sol"


async def retrieve_all(settings: Settings, questions: list[str]) -> list[list[str]]:
    """Each chunk's full text, header lines included, as the model would see it."""
    retriever = QdrantRetriever(settings)
    limit = asyncio.Semaphore(CONCURRENT_RETRIEVALS)

    async def retrieve(question: str) -> list[str]:
        async with limit:
            return [c.text for c in await retriever.retrieve(question, settings.retrieval_k)]

    try:
        return await asyncio.gather(*(retrieve(q) for q in questions))
    finally:
        await retriever.close()


def collection_chunk_count(settings: Settings) -> int:
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=10
    )
    try:
        if not client.collection_exists(settings.collection_name):
            raise SystemExit(f"Collection {settings.collection_name} doesn't exist; ingest first")
        return client.count(settings.collection_name, exact=True).count
    finally:
        client.close()


def chunk_sizes(settings: Settings) -> tuple[int, int]:
    """The size limit and overlap Settings gives, falling back to the version's defaults.

    This is what ingestion with the same Settings would use; the collection doesn't record it.
    """
    if settings.chunking_version not in STRATEGIES:
        raise SystemExit(f"Unknown CHUNKING_VERSION {settings.chunking_version}")
    defaults = inspect.signature(STRATEGIES[settings.chunking_version]).parameters
    max_tokens = settings.chunk_max_tokens or defaults["max_tokens"].default
    overlap = settings.chunk_overlap_tokens
    return max_tokens, overlap if overlap is not None else defaults["overlap_tokens"].default


def mean_scores(rows: list[dict[str, float]], metric_names: list[str]) -> dict[str, float]:
    return {
        "questions": len(rows),
        **{name: round(fmean(row[name] for row in rows), 4) for name in metric_names},
    }


def write_report(
    path: Path,
    summary: dict[str, Any],
    goldens: list[Golden],
    contexts: list[list[str]],
    reasons: dict[str, dict[str, str]],
    metric_names: list[str],
) -> None:
    """The run's results as Markdown, for VS Code's preview or GitHub. Lowest scores first."""
    settings = summary["hyperparameters"]
    empty = summary["empty_retrievals"]
    empty_ids = f" (scored 0): {', '.join(empty)}" if empty else ""
    lines = [
        f"# Retriever eval, {summary['run_at']}",
        "",
        f"`{settings['chunking_version']}` · k={settings['retrieval_k']} · "
        f"threshold {settings['retrieval_score_threshold']} · judge `{settings['judge_model']}` · "
        f"{settings['goldens_used']} questions · judge cost ${summary['judge_cost_usd']:.2f}",
        "",
        "<details><summary>All settings</summary>",
        "",
        *[f"- `{name}`: `{value}`" for name, value in settings.items()],
        f"- DeepEval run file: `{summary['deepeval_run_file']}`",
        "",
        "</details>",
        "",
        "## Scores",
        "",
        f"| | {' | '.join(metric_names)} | Questions |",
        f"|---|{'---|' * len(metric_names)}---|",
        *[
            f"| {group} | {' | '.join(f'{row[n]:.3f}' for n in metric_names)} "
            f"| {row['questions']} |"
            for group, row in summary["means"].items()
        ],
        "",
        f"Questions with no chunk retrieved: {len(empty)}{empty_ids}",
        "",
        "## Questions, lowest score first",
        "",
    ]
    rows = sorted(
        zip(summary["questions"], goldens, contexts, strict=True),
        key=lambda row: min(row[0]["scores"].values()),
    )
    for question, golden, context in rows:
        question_id = question["question_id"]
        scores = " · ".join(f"{n} {question['scores'][n]:.2f}" for n in metric_names)
        lines += [
            f"<details><summary><b>{question_id}</b> · {question['category']} · {scores}</summary>",
            "",
            f"**Question.** {golden.input}",
            "",
            f"**Expected answer.** {golden.expected_output}",
            "",
        ]
        if not context:
            lines += ["No chunk passed the score threshold, so the judge wasn't asked.", ""]
        for name in metric_names:
            reason = reasons.get(question_id, {}).get(name)
            if reason:
                lines += [f"**{name} {question['scores'][name]:.2f}.** {reason}", ""]
        for rank, chunk in enumerate(context, start=1):
            header, _, body = chunk.partition("\n\n")
            excerpt = body[:REPORT_EXCERPT_CHARS] + (
                "…" if len(body) > REPORT_EXCERPT_CHARS else ""
            )
            lines += [
                f"**Chunk {rank}.** {' — '.join(header.splitlines())}",
                "",
                "```text",
                excerpt,
                "```",
                "",
            ]
        lines += ["</details>", ""]
    lines.append(
        f"Full chunk text and the judge's verdicts are in `{summary['deepeval_run_file']}`."
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the retriever eval (ADR 0006).")
    parser.add_argument("--judge-model", help="Overrides EVAL_JUDGE_MODEL (default gpt-6-sol)")
    parser.add_argument(
        "--limit", type=int, help="Run only the first N goldens, as a cheap smoke test"
    )
    args = parser.parse_args()

    settings = Settings()
    judge_model = args.judge_model or EvalSettings().eval_judge_model
    max_tokens, overlap_tokens = chunk_sizes(settings)
    hyperparameters: dict[str, str | int | float] = {
        "chunking_version": settings.chunking_version,
        "chunk_max_tokens": max_tokens,
        "chunk_overlap_tokens": overlap_tokens,
        "embedding_model": settings.embedding_model,
        "collection_name": settings.collection_name,
        "collection_chunk_count": collection_chunk_count(settings),
        "retrieval_k": settings.retrieval_k,
        "retrieval_score_threshold": settings.retrieval_score_threshold,
        "judge_model": judge_model,
        "goldens_file": GOLDENS.name,
        "goldens_sha256": hashlib.sha256(GOLDENS.read_bytes()).hexdigest(),
    }

    goldens = [Golden(**json.loads(line)) for line in GOLDENS.read_text().splitlines()]
    goldens = goldens[: args.limit]
    hyperparameters["goldens_used"] = len(goldens)
    contexts = asyncio.run(retrieve_all(settings, [g.input for g in goldens]))

    # A question with no chunk above the score threshold isn't sent to the judge; it scores 0.
    test_cases = [
        LLMTestCase(
            name=golden.additional_metadata["question_id"],
            input=golden.input,
            expected_output=golden.expected_output,
            retrieval_context=context,
            metadata=golden.additional_metadata,
        )
        for golden, context in zip(goldens, contexts, strict=True)
        if context
    ]

    judge = OpenAIModel(model=judge_model, api_key=settings.openai_api_key.get_secret_value())
    # Only scores are recorded. evaluate() refuses metrics without a threshold, so 0 makes every
    # case pass. eval_mode is pinned so DEEPEVAL_EVAL_MODE can't swap the judge for another model.
    metrics = [
        ContextualRecallMetric(threshold=0, model=judge, eval_mode="llm"),
        ContextualPrecisionMetric(threshold=0, model=judge, eval_mode="llm"),
    ]
    metric_names = [metric.__name__ for metric in metrics]

    started = datetime.now(UTC)
    RESULTS.mkdir(parents=True, exist_ok=True)
    scores: dict[str, dict[str, float]] = {}
    reasons: dict[str, dict[str, str]] = {}
    cost = 0.0
    run_file = None
    if test_cases:
        result = evaluate(
            test_cases=test_cases,
            metrics=metrics,
            hyperparameters=hyperparameters,
            async_config=AsyncConfig(max_concurrent=10),
            display_config=DisplayConfig(
                print_results=False, inspect_after_run=False, results_folder=str(RESULTS)
            ),
            cache_config=CacheConfig(write_cache=False),
        )
        for test_result in result.test_results:
            metrics_data = test_result.metrics_data or []
            scores[test_result.name] = {m.name: m.score for m in metrics_data}
            reasons[test_result.name] = {m.name: m.reason for m in metrics_data if m.reason}
            cost += sum(m.evaluation_cost or 0 for m in metrics_data)
        # DeepEval doesn't return the file it wrote, so take the newest.
        run_file = max(RESULTS.glob("test_run_*.json"), key=lambda p: p.stat().st_mtime).name

    zero = dict.fromkeys(metric_names, 0.0)
    questions = [
        {
            "question_id": golden.additional_metadata["question_id"],
            "category": golden.additional_metadata["category"],
            "retrieved": bool(context),
            "scores": scores.get(golden.additional_metadata["question_id"], zero),
        }
        for golden, context in zip(goldens, contexts, strict=True)
    ]
    categories = sorted({q["category"] for q in questions})
    means = {
        "overall": mean_scores([q["scores"] for q in questions], metric_names),
        **{
            category: mean_scores(
                [q["scores"] for q in questions if q["category"] == category], metric_names
            )
            for category in categories
        },
    }
    empty = [q["question_id"] for q in questions if not q["retrieved"]]

    summary_path = RESULTS / f"summary_{started:%Y%m%d_%H%M%S}.json"
    summary = {
        "run_at": started.isoformat(timespec="seconds"),
        "deepeval_run_file": run_file,
        "judge_cost_usd": round(cost, 4),
        "hyperparameters": hyperparameters,
        "empty_retrievals": empty,
        "means": means,
        "questions": questions,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    report_path = RESULTS / f"report_{started:%Y%m%d_%H%M%S}.md"
    write_report(report_path, summary, goldens, contexts, reasons, metric_names)

    width = max(len(group) for group in means)
    print(f"\n{'':<{width}}  {'  '.join(f'{n:>20}' for n in metric_names)}  questions")
    for group, row in means.items():
        values = "  ".join(f"{row[n]:>20.3f}" for n in metric_names)
        print(f"{group:<{width}}  {values}  {row['questions']:>9}")
    ids = f" (scored 0): {', '.join(empty)}" if empty else ""
    print(f"\nQuestions with no chunk retrieved: {len(empty)}{ids}")
    print(f"Judge cost: ${cost:.2f}")
    print(f"Wrote {summary_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
