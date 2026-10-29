"""Run the pipeline eval: the app's retriever and Answerer together, over the pipeline goldens.

Run from the repo root:  uv run --project backend --group evals python evals/pipeline/run_eval.py

Answers each golden with the app's QdrantRetriever, OpenAIChatModel and Settings. The judge model
scores Answers for Faithfulness, Answer Relevancy, Contextual Recall, Contextual Relevancy and
Citation Faithfulness;
citation precision and recall against the gold sections, and whether the Response Type is the
expected one, are worked out without it. Writes to evals/results/pipeline/: DeepEval's two
test_run_*.json files, one per group of judged metrics; a summary_*.json with each reply, the
scores by question and category and the settings the run used; and a report_*.md that shows the
same results for reading. See ADR 0006.
"""

# ruff: noqa: E402  (the environment must be set before deepeval is imported)

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
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
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.metrics.base_metric import BaseMetric
from deepeval.metrics.community import CitationFaithfulnessMetric
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase
from langchain_core.messages import BaseMessage
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import QdrantClient

from hr_assist.answering import ChatModel
from hr_assist.answering.adapters import OpenAIChatModel, QdrantRetriever
from hr_assist.answering.answerer import Answerer, Retriever
from hr_assist.answering.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    GeneratedReply,
)
from hr_assist.answering.prompt import PROMPT_VERSION
from hr_assist.corpus import Chunk
from hr_assist.errors import UpstreamError
from hr_assist.ingestion import STRATEGIES
from hr_assist.settings import REPO_ROOT, REPO_ROOT_ENV_FILE, Settings

GOLDENS = Path(__file__).resolve().parent / "goldens_v1.jsonl"
RESULTS = REPO_ROOT / "evals" / "results" / "pipeline"
CONCURRENT_ANSWERS = 8
# A source marker such as [2] or [1, 3], with the space before it. The triad's judge reads the
# reply without them; answerer.py has the same pattern.
SOURCE_MARKER = re.compile(r"\s?\[\d+(?:\s*,\s*\d+)*\]")

CITATION_PRECISION = "Citation Precision"
CITATION_RECALL = "Citation Recall"
RESPONSE_TYPE_MATCH = "Response Type Match"


class EvalSettings(BaseSettings):
    """Eval-only settings. The API never uses the judge, so it isn't in the app's Settings."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    eval_judge_model: str = "gpt-5.6-luna"


class RecordingRetriever:
    """Passes searches to the real retriever and keeps the chunks it returned."""

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever
        self.chunks: list[Chunk] = []

    async def retrieve(self, query: str, k: int) -> list[Chunk]:
        self.chunks = await self._retriever.retrieve(query, k)
        return self.chunks


class UsageRecordingModel:
    """Passes calls to the chat model and keeps their token usage, which ChatResponse drops."""

    def __init__(self, model: ChatModel) -> None:
        self._model = model
        self.token_usage: dict[str, int] = {}

    async def generate(self, messages: list[BaseMessage]) -> GeneratedReply:
        generated = await self._model.generate(messages)
        for name, count in generated.token_usage.items():
            self.token_usage[name] = self.token_usage.get(name, 0) + count
        return generated


@dataclass
class Generated:
    """One golden's reply and what was retrieved for it, or the error that stopped it."""

    response: ChatResponse | None
    retrieved: list[Chunk] = field(default_factory=list)
    error: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)

    @property
    def cited(self) -> list[Chunk]:
        """The retrieved chunk behind each citation, in citation order, so [n] is the n-th."""
        if self.response is None:
            return []
        return [
            next(
                c
                for c in self.retrieved
                if c.metadata.document_id == citation.document_id and c.body == citation.snippet
            )
            for citation in self.response.citations
        ]


async def generate_all(settings: Settings, goldens: list[Golden]) -> list[Generated]:
    retriever = QdrantRetriever(settings)
    model = OpenAIChatModel(settings)
    limit = asyncio.Semaphore(CONCURRENT_ANSWERS)

    async def generate(golden: Golden) -> Generated:
        recording = RecordingRetriever(retriever)
        recorder = UsageRecordingModel(model)
        answerer = Answerer(recording, recorder, settings.retrieval_k, settings.history_turns)
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=golden.input)],
            as_of_date=date.fromisoformat(golden.additional_metadata["as_of_date"]),
        )
        async with limit:
            try:
                response = await answerer.answer(request)
            except UpstreamError as exc:
                return Generated(
                    response=None,
                    retrieved=recording.chunks,
                    error=str(exc),
                    token_usage=recorder.token_usage,
                )
        return Generated(
            response=response, retrieved=recording.chunks, token_usage=recorder.token_usage
        )

    try:
        return await asyncio.gather(*(generate(g) for g in goldens))
    finally:
        await retriever.close()


def hits(chunk: Chunk, target: dict[str, Any]) -> bool:
    """Whether a cited chunk is the target's section or one of its subsections, or its slide."""
    m = chunk.metadata
    if m.document_id != target["document_id"]:
        return False
    if "slide" in target:
        return m.slide == target["slide"]
    section = target["section"]
    return bool(m.section_number) and (
        m.section_number == section or m.section_number.startswith(f"{section}.")
    )


def citation_scores(golden: Golden, g: Generated) -> dict[str, float]:
    """Citation precision and recall against the gold sections. No citations scores 0 on both."""
    targets = golden.additional_metadata["citation_targets"]
    cited = g.cited
    if not cited:
        return {CITATION_PRECISION: 0.0, CITATION_RECALL: 0.0}
    return {
        CITATION_PRECISION: sum(any(hits(c, t) for t in targets) for c in cited) / len(cited),
        CITATION_RECALL: sum(any(hits(c, t) for c in cited) for t in targets) / len(targets),
    }


def is_answer(g: Generated) -> bool:
    return g.response is not None and g.response.response_type == "answer"


def expects_answer(golden: Golden) -> bool:
    return golden.additional_metadata["expected_response_type"] == "answer"


def triad_cases(goldens: list[Golden], generated: list[Generated]) -> list[LLMTestCase]:
    """Answers to Answer questions, judged against every chunk retrieved, markers removed."""
    return [
        LLMTestCase(
            name=golden.additional_metadata["question_id"],
            input=golden.input,
            actual_output=SOURCE_MARKER.sub("", g.response.message),
            expected_output=golden.expected_output,
            retrieval_context=[c.text for c in g.retrieved],
            metadata=golden.additional_metadata,
        )
        for golden, g in zip(goldens, generated, strict=True)
        if expects_answer(golden) and is_answer(g)
    ]


def citation_cases(goldens: list[Golden], generated: list[Generated]) -> list[LLMTestCase]:
    """Answers with citations, judged against the cited chunks in citation order, markers kept."""
    return [
        LLMTestCase(
            name=golden.additional_metadata["question_id"],
            input=golden.input,
            actual_output=g.response.message,
            retrieval_context=[c.text for c in g.cited],
            metadata=golden.additional_metadata,
        )
        for golden, g in zip(goldens, generated, strict=True)
        if expects_answer(golden) and is_answer(g) and g.response.citations
    ]


@dataclass
class Judged:
    scores: dict[str, dict[str, float]] = field(default_factory=dict)
    reasons: dict[str, dict[str, str]] = field(default_factory=dict)
    cost: float = 0.0
    run_files: list[str] = field(default_factory=list)


def judge_cases(
    cases: list[LLMTestCase],
    metrics: list[BaseMetric],
    hyperparameters: dict[str, str | int | float],
    judged: Judged,
) -> None:
    if not cases:
        return
    result = evaluate(
        test_cases=cases,
        metrics=metrics,
        hyperparameters=hyperparameters,
        async_config=AsyncConfig(max_concurrent=10),
        display_config=DisplayConfig(
            print_results=False,
            inspect_after_run=False,
            results_folder=str(RESULTS),
        ),
        cache_config=CacheConfig(write_cache=False),
    )
    for test_result in result.test_results:
        metrics_data = test_result.metrics_data or []
        judged.scores.setdefault(test_result.name, {}).update(
            {m.name: m.score for m in metrics_data}
        )
        judged.reasons.setdefault(test_result.name, {}).update(
            {m.name: m.reason for m in metrics_data if m.reason}
        )
        judged.cost += sum(m.evaluation_cost or 0 for m in metrics_data)
    # DeepEval doesn't return the file it wrote, so take the newest.
    judged.run_files.append(
        max(RESULTS.glob("test_run_*.json"), key=lambda p: p.stat().st_mtime).name
    )


def question_rows(
    goldens: list[Golden],
    generated: list[Generated],
    judged: Judged,
    answer_metrics: list[str],
) -> list[dict[str, Any]]:
    rows = []
    for golden, g in zip(goldens, generated, strict=True):
        meta = golden.additional_metadata
        question_id = meta["question_id"]
        expected = meta["expected_response_type"]
        response_type = g.response.response_type if g.response else None
        scores: dict[str, float] = {}
        if expected == "answer":
            scores = dict.fromkeys(answer_metrics, 0.0)
            if is_answer(g):
                scores |= citation_scores(golden, g) | judged.scores.get(question_id, {})
        scores[RESPONSE_TYPE_MATCH] = float(response_type == expected)
        cited = g.cited
        rows.append(
            {
                "question_id": question_id,
                "category": meta["category"],
                "expected_response_type": expected,
                "response_type": response_type,
                "message": g.response.message if g.response else None,
                "retrieved": [c.id for c in g.retrieved],
                "citations": [
                    {
                        "document_id": c.metadata.document_id,
                        "section_number": c.metadata.section_number,
                        "slide": c.metadata.slide,
                        "hit": any(hits(c, t) for t in meta["citation_targets"]),
                    }
                    for c in cited
                ],
                "error": g.error,
                "token_usage": g.token_usage,
                "scores": scores,
            }
        )
    return rows


def mean_scores(rows: list[dict[str, float]], metric_names: list[str]) -> dict[str, float]:
    return {
        "questions": len(rows),
        **{name: round(fmean(row[name] for row in rows), 4) for name in metric_names},
    }


def total_tokens(questions: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for question in questions:
        for name, count in question["token_usage"].items():
            totals[name] = totals.get(name, 0) + count
    return totals


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


def score_table(means: dict[str, dict[str, float]], metric_names: list[str]) -> list[str]:
    return [
        f"| | {' | '.join(metric_names)} | Questions |",
        f"|---|{'---|' * len(metric_names)}---|",
        *[
            f"| {group} | {' | '.join(f'{row[n]:.3f}' for n in metric_names)} "
            f"| {row['questions']} |"
            for group, row in means.items()
        ],
    ]


def id_list(label: str, ids: list[str]) -> str:
    return f"{label}: {len(ids)}" + (f": {', '.join(ids)}" if ids else "")


def write_report(
    path: Path,
    summary: dict[str, Any],
    goldens: list[Golden],
    generated: list[Generated],
    reasons: dict[str, dict[str, str]],
    answer_metrics: list[str],
) -> None:
    """The run's results as Markdown, for VS Code's preview or GitHub. Lowest scores first."""
    settings = summary["hyperparameters"]
    lines = [
        f"# Pipeline eval, {summary['run_at']}",
        "",
        f"`{settings['chat_model']}` (reasoning {settings['reasoning_effort']}) · "
        f"prompt {settings['prompt_version']} · `{settings['chunking_version']}` · "
        f"k={settings['retrieval_k']} · threshold {settings['retrieval_score_threshold']} · "
        f"judge `{settings['judge_model']}` · {settings['goldens_used']} questions · "
        f"judge cost ${summary['judge_cost_usd']:.2f}",
        "",
        "<details><summary>All settings</summary>",
        "",
        *[f"- `{name}`: `{value}`" for name, value in settings.items()],
        f"- Generator tokens: `{summary['generator_tokens']}`",
        f"- DeepEval run files: {', '.join(f'`{f}`' for f in summary['deepeval_run_files'])}",
        "",
        "</details>",
        "",
    ]
    if summary["means"]["answers"]:
        lines += [
            "## Answer questions",
            "",
            f"{RESPONSE_TYPE_MATCH} here is the share of questions answered.",
            "",
            *score_table(summary["means"]["answers"], [*answer_metrics, RESPONSE_TYPE_MATCH]),
            "",
            id_list("Replies that weren't an Answer (scored 0)", summary["non_answers"]),
            "",
            id_list("Questions with no chunk retrieved (scored 0)", summary["empty_retrievals"]),
            "",
            id_list("Generation errors (scored 0)", summary["generation_errors"]),
            "",
        ]
    if summary["means"]["other_response_types"]:
        lines += [
            "## Clarification, Abstention and Refusal questions",
            "",
            *score_table(summary["means"]["other_response_types"], [RESPONSE_TYPE_MATCH]),
            "",
        ]
    lines += ["## Questions, lowest score first", ""]
    rows = sorted(
        zip(summary["questions"], goldens, generated, strict=True),
        key=lambda row: min(row[0]["scores"].values()),
    )
    for question, golden, g in rows:
        question_id = question["question_id"]
        expected = question["expected_response_type"]
        scores = " · ".join(f"{n} {s:.2f}" for n, s in question["scores"].items())
        lines += [
            f"<details><summary><b>{question_id}</b> · {question['category']} · "
            f"{question['response_type'] or 'error'} (expected {expected}) · {scores}</summary>",
            "",
            f"**Question.** {golden.input}",
            "",
            f"**Expected answer ({expected}).** {golden.expected_output}",
            "",
        ]
        if question["error"]:
            lines += [f"**Error.** {question['error']}", ""]
        else:
            lines += [
                f"**Reply ({question['response_type']}).**",
                "",
                *[f"> {line}" for line in question["message"].splitlines()],
                "",
            ]
            if expected == "answer" and question["response_type"] != "answer":
                lines += ["Not an Answer, so the judge wasn't asked.", ""]
        for name, reason in reasons.get(question_id, {}).items():
            lines += [f"**{name} {question['scores'][name]:.2f}.** {reason}", ""]
        if expected == "answer":
            targets = golden.additional_metadata["citation_targets"]
            cited = g.cited
            lines += ["**Gold sections.**", ""]
            for target in targets:
                where = f"slide {target['slide']}" if "slide" in target else target["section"]
                found = "cited" if any(hits(c, target) for c in cited) else "not cited"
                lines.append(f"- {target['document_id']} {where}: {found}")
            for passage in golden.additional_metadata["unreachable_passages"]:
                lines.append(f"- {passage}: can't be cited, not a target")
            lines.append("")
        if g.retrieved:
            cited_ids = [c.id for c in g.cited]
            lines += ["**Retrieved chunks.**", ""]
            for rank, chunk in enumerate(g.retrieved, start=1):
                header = " — ".join(chunk.text.partition("\n\n")[0].splitlines())
                mark = ""
                if chunk.id in cited_ids:
                    number = cited_ids.index(chunk.id) + 1
                    hit = any(
                        hits(chunk, t) for t in golden.additional_metadata["citation_targets"]
                    )
                    mark = f" · cited as [{number}], {'a gold section' if hit else 'not gold'}"
                lines.append(f"{rank}. {header}{mark}")
            lines.append("")
        else:
            lines += ["No chunk passed the score threshold.", ""]
        lines += ["</details>", ""]
    lines.append(
        "Full chunk text and the judge's verdicts are in "
        f"{', '.join(f'`{f}`' for f in summary['deepeval_run_files'])}."
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline eval (ADR 0006).")
    parser.add_argument("--judge-model", help="Overrides EVAL_JUDGE_MODEL (default gpt-5.6-luna)")
    parser.add_argument(
        "--limit", type=int, help="Run only the first N goldens, as a cheap smoke test"
    )
    args = parser.parse_args()

    settings = Settings()
    judge_model = args.judge_model or EvalSettings().eval_judge_model
    max_tokens, overlap_tokens = chunk_sizes(settings)
    goldens = [Golden(**json.loads(line)) for line in GOLDENS.read_text().splitlines()]
    goldens = goldens[: args.limit]
    hyperparameters: dict[str, str | int | float] = {
        "chat_model": settings.chat_model,
        "reasoning_effort": settings.reasoning_effort,
        "max_output_tokens": settings.max_output_tokens,
        "prompt_version": PROMPT_VERSION,
        "chunking_version": settings.chunking_version,
        "chunk_max_tokens": max_tokens,
        "chunk_overlap_tokens": overlap_tokens,
        "embedding_model": settings.embedding_model,
        "collection_name": settings.collection_name,
        "collection_chunks": collection_chunk_count(settings),
        "retrieval_k": settings.retrieval_k,
        "retrieval_score_threshold": settings.retrieval_score_threshold,
        "judge_model": judge_model,
        "goldens_file": GOLDENS.name,
        "goldens_sha256": hashlib.sha256(GOLDENS.read_bytes()).hexdigest(),
        "goldens_used": len(goldens),
    }

    started = datetime.now(UTC)
    generated = asyncio.run(generate_all(settings, goldens))

    judge = OpenAIModel(model=judge_model, api_key=settings.openai_api_key.get_secret_value())
    # Only scores are recorded. evaluate() refuses metrics without a threshold, so 0 makes every
    # case pass. eval_mode is pinned so DEEPEVAL_EVAL_MODE can't swap the judge for another model.
    # The RAG triad, plus Contextual Relevancy: what share of the retrieved text is about the
    # question. It reads the same test cases, so it joins the triad's run.
    triad = [
        FaithfulnessMetric(threshold=0, model=judge, eval_mode="llm"),
        AnswerRelevancyMetric(threshold=0, model=judge, eval_mode="llm"),
        ContextualRecallMetric(threshold=0, model=judge, eval_mode="llm"),
        ContextualRelevancyMetric(threshold=0, model=judge, eval_mode="llm"),
    ]
    citation = [CitationFaithfulnessMetric(threshold=0, model=judge, eval_mode="llm")]
    answer_metrics = [
        *(metric.__name__ for metric in triad + citation),
        CITATION_PRECISION,
        CITATION_RECALL,
    ]

    RESULTS.mkdir(parents=True, exist_ok=True)
    judged = Judged()
    # Two runs, because the triad reads the reply without markers against every retrieved chunk,
    # and Citation Faithfulness reads the markers against the cited chunks.
    judge_cases(triad_cases(goldens, generated), triad, hyperparameters, judged)
    judge_cases(citation_cases(goldens, generated), citation, hyperparameters, judged)

    questions = question_rows(goldens, generated, judged, answer_metrics)
    answers = [q for q in questions if q["expected_response_type"] == "answer"]
    others = [q for q in questions if q["expected_response_type"] != "answer"]
    answer_names = [*answer_metrics, RESPONSE_TYPE_MATCH]
    means: dict[str, dict[str, dict[str, float]]] = {"answers": {}, "other_response_types": {}}
    if answers:
        means["answers"] = {
            "overall": mean_scores([q["scores"] for q in answers], answer_names),
            **{
                category: mean_scores(
                    [q["scores"] for q in answers if q["category"] == category], answer_names
                )
                for category in sorted({q["category"] for q in answers})
            },
        }
    if others:
        means["other_response_types"] = {
            "overall": mean_scores([q["scores"] for q in others], [RESPONSE_TYPE_MATCH]),
            **{
                expected: mean_scores(
                    [q["scores"] for q in others if q["expected_response_type"] == expected],
                    [RESPONSE_TYPE_MATCH],
                )
                for expected in ("clarification", "abstention", "refusal")
                if any(q["expected_response_type"] == expected for q in others)
            },
        }
    non_answers = [
        q["question_id"]
        for q in answers
        if q["response_type"] not in (None, "answer") and q["retrieved"]
    ]
    empty = [q["question_id"] for q in answers if not q["retrieved"] and not q["error"]]
    errors = [q["question_id"] for q in questions if q["error"]]
    tokens = total_tokens(questions)

    summary_path = RESULTS / f"summary_{started:%Y%m%d_%H%M%S}.json"
    summary = {
        "run_at": started.isoformat(timespec="seconds"),
        "deepeval_run_files": judged.run_files,
        "judge_cost_usd": round(judged.cost, 4),
        "generator_tokens": tokens,
        "hyperparameters": hyperparameters,
        "non_answers": non_answers,
        "empty_retrievals": empty,
        "generation_errors": errors,
        "means": means,
        "questions": questions,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    report_path = RESULTS / f"report_{started:%Y%m%d_%H%M%S}.md"
    write_report(report_path, summary, goldens, generated, judged.reasons, answer_metrics)

    for title, group, names in (
        ("Answer questions", means["answers"], answer_names),
        ("Other response types", means["other_response_types"], [RESPONSE_TYPE_MATCH]),
    ):
        if not group:
            continue
        width = max(len(name) for name in group)
        print(f"\n{title}")
        print(f"{'':<{width}}  {'  '.join(f'{n:>22}' for n in names)}  questions")
        for name, row in group.items():
            values = "  ".join(f"{row[n]:>22.3f}" for n in names)
            print(f"{name:<{width}}  {values}  {row['questions']:>9}")
    print(f"\n{id_list("Replies to Answer questions that weren't an Answer", non_answers)}")
    print(id_list("Questions with no chunk retrieved", empty))
    print(id_list("Generation errors", errors))
    print(f"Generator tokens: {tokens}")
    print(f"Judge cost: ${judged.cost:.2f}")
    print(f"Wrote {summary_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
