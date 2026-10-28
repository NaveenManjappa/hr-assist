"""Run the generation eval: Faithfulness and Answer Relevancy over the generation goldens.

Run from the repo root:  uv run --project backend --group evals python evals/generation/run_eval.py

Hands the app's Answerer each golden's gold chunks through a fake retriever, has the judge model
score the replies, and writes three files to evals/results/generation/: DeepEval's
test_run_*.json, with every verdict and reason; a summary_*.json with each reply, the scores by
question and category and the settings the run used; and a report_*.md that shows the same
results for reading. See ADR 0006.
"""

# ruff: noqa: E402  (the environment must be set before deepeval is imported)

import argparse
import asyncio
import hashlib
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
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase
from langchain_core.messages import BaseMessage
from pydantic_settings import BaseSettings, SettingsConfigDict

from hr_assist.answering import ChatModel
from hr_assist.answering.adapters import OpenAIChatModel
from hr_assist.answering.answerer import Answerer
from hr_assist.answering.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    GeneratedReply,
)
from hr_assist.answering.prompt import PROMPT_VERSION
from hr_assist.corpus import Chunk
from hr_assist.errors import UpstreamError
from hr_assist.settings import REPO_ROOT, REPO_ROOT_ENV_FILE, Settings

GOLDENS = Path(__file__).resolve().parent / "goldens_v1.jsonl"
RESULTS = REPO_ROOT / "evals" / "results" / "generation"
CONCURRENT_ANSWERS = 8
# A source marker such as [2] or [1, 3], with the space before it. The judge reads the reply
# without them; answerer.py has the same pattern.
SOURCE_MARKER = re.compile(r"\s?\[\d+(?:\s*,\s*\d+)*\]")


class EvalSettings(BaseSettings):
    """Eval-only settings. The API never uses the judge, so it isn't in the app's Settings."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    eval_judge_model: str = "gpt-5.6-luna"


class FixedRetriever:
    """Returns one golden's gold chunks, whatever the query and k."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks

    async def retrieve(self, query: str, k: int) -> list[Chunk]:
        return self._chunks


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
    """One golden's reply, or the error that stopped it."""

    response: ChatResponse | None
    error: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)


async def generate_all(
    model: ChatModel, goldens: list[Golden], history_turns: int
) -> list[Generated]:
    limit = asyncio.Semaphore(CONCURRENT_ANSWERS)

    async def generate(golden: Golden) -> Generated:
        meta = golden.additional_metadata
        chunks = [Chunk.model_validate(chunk) for chunk in meta["chunks"]]
        recorder = UsageRecordingModel(model)
        # The fake retriever ignores k, so its value has no effect.
        answerer = Answerer(FixedRetriever(chunks), recorder, len(chunks), history_turns)
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=golden.input)],
            as_of_date=date.fromisoformat(meta["as_of_date"]),
        )
        async with limit:
            try:
                response = await answerer.answer(request)
            except UpstreamError as exc:
                return Generated(response=None, error=str(exc), token_usage=recorder.token_usage)
        return Generated(response=response, token_usage=recorder.token_usage)

    return await asyncio.gather(*(generate(g) for g in goldens))


def judged_cases(goldens: list[Golden], generated: list[Generated]) -> list[LLMTestCase]:
    """Only Answers are judged; any other reply, or an error, scores 0 without the judge."""
    return [
        LLMTestCase(
            name=golden.additional_metadata["question_id"],
            input=golden.input,
            actual_output=SOURCE_MARKER.sub("", g.response.message),
            expected_output=golden.expected_output,
            retrieval_context=golden.retrieval_context,
            metadata={k: v for k, v in golden.additional_metadata.items() if k != "chunks"},
        )
        for golden, g in zip(goldens, generated, strict=True)
        if g.response is not None and g.response.response_type == "answer"
    ]


def question_rows(
    goldens: list[Golden],
    generated: list[Generated],
    scores: dict[str, dict[str, float]],
    metric_names: list[str],
) -> list[dict[str, Any]]:
    zero = dict.fromkeys(metric_names, 0.0)
    rows = []
    for golden, g in zip(goldens, generated, strict=True):
        question_id = golden.additional_metadata["question_id"]
        rows.append(
            {
                "question_id": question_id,
                "category": golden.additional_metadata["category"],
                "response_type": g.response.response_type if g.response else None,
                "message": g.response.message if g.response else None,
                "cited_sources": len(g.response.citations) if g.response else 0,
                "error": g.error,
                "token_usage": g.token_usage,
                "scores": scores.get(question_id, zero),
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


def write_report(
    path: Path,
    summary: dict[str, Any],
    goldens: list[Golden],
    reasons: dict[str, dict[str, str]],
    metric_names: list[str],
) -> None:
    """The run's results as Markdown, for VS Code's preview or GitHub. Lowest scores first."""
    settings = summary["hyperparameters"]
    non_answers = summary["non_answers"]
    errors = summary["generation_errors"]
    lines = [
        f"# Generation eval, {summary['run_at']}",
        "",
        f"`{settings['chat_model']}` (reasoning {settings['reasoning_effort']}) · "
        f"prompt {settings['prompt_version']} · `{settings['chunking_version']}` · "
        f"judge `{settings['judge_model']}` · {settings['goldens_used']} questions · "
        f"judge cost ${summary['judge_cost_usd']:.2f}",
        "",
        "<details><summary>All settings</summary>",
        "",
        *[f"- `{name}`: `{value}`" for name, value in settings.items()],
        f"- Generator tokens: `{summary['generator_tokens']}`",
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
        f"Replies that weren't an Answer (scored 0): {len(non_answers)}"
        + (f": {', '.join(non_answers)}" if non_answers else ""),
        "",
        f"Generation errors (scored 0): {len(errors)}"
        + (f": {', '.join(errors)}" if errors else ""),
        "",
        "## Questions, lowest score first",
        "",
    ]
    rows = sorted(
        zip(summary["questions"], goldens, strict=True),
        key=lambda row: min(row[0]["scores"].values()),
    )
    for question, golden in rows:
        question_id = question["question_id"]
        scores = " · ".join(f"{n} {question['scores'][n]:.2f}" for n in metric_names)
        lines += [
            f"<details><summary><b>{question_id}</b> · {question['category']} · "
            f"{question['response_type'] or 'error'} · {scores}</summary>",
            "",
            f"**Question.** {golden.input}",
            "",
            f"**Expected answer.** {golden.expected_output}",
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
            if question["response_type"] != "answer":
                lines += ["Not an Answer, so the judge wasn't asked.", ""]
        for name in metric_names:
            reason = reasons.get(question_id, {}).get(name)
            if reason:
                lines += [f"**{name} {question['scores'][name]:.2f}.** {reason}", ""]
        lines += ["**Gold chunks.**", ""]
        for number, chunk in enumerate(golden.retrieval_context, start=1):
            header = chunk.partition("\n\n")[0]
            lines.append(f"{number}. {' — '.join(header.splitlines())}")
        lines += ["", "</details>", ""]
    lines.append(
        "Full chunk text is in the goldens file, and the judge's verdicts are in "
        f"`{summary['deepeval_run_file']}`."
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the generation eval (ADR 0006).")
    parser.add_argument("--judge-model", help="Overrides EVAL_JUDGE_MODEL (default gpt-5.6-luna)")
    parser.add_argument(
        "--limit", type=int, help="Run only the first N goldens, as a cheap smoke test"
    )
    args = parser.parse_args()

    settings = Settings()
    judge_model = args.judge_model or EvalSettings().eval_judge_model
    goldens = [Golden(**json.loads(line)) for line in GOLDENS.read_text().splitlines()]
    goldens = goldens[: args.limit]
    hyperparameters: dict[str, str | int | float] = {
        "chat_model": settings.chat_model,
        "reasoning_effort": settings.reasoning_effort,
        "max_output_tokens": settings.max_output_tokens,
        "prompt_version": PROMPT_VERSION,
        "chunking_version": goldens[0].additional_metadata["chunking_version"],
        "judge_model": judge_model,
        "goldens_file": GOLDENS.name,
        "goldens_sha256": hashlib.sha256(GOLDENS.read_bytes()).hexdigest(),
        "goldens_used": len(goldens),
    }

    started = datetime.now(UTC)
    generated = asyncio.run(
        generate_all(OpenAIChatModel(settings), goldens, settings.history_turns)
    )
    cases = judged_cases(goldens, generated)

    judge = OpenAIModel(model=judge_model, api_key=settings.openai_api_key.get_secret_value())
    # Only scores are recorded. evaluate() refuses metrics without a threshold, so 0 makes every
    # case pass. eval_mode is pinned so DEEPEVAL_EVAL_MODE can't swap the judge for another model.
    metrics = [
        FaithfulnessMetric(threshold=0, model=judge, eval_mode="llm"),
        AnswerRelevancyMetric(threshold=0, model=judge, eval_mode="llm"),
    ]
    metric_names = [metric.__name__ for metric in metrics]

    RESULTS.mkdir(parents=True, exist_ok=True)
    scores: dict[str, dict[str, float]] = {}
    reasons: dict[str, dict[str, str]] = {}
    cost = 0.0
    run_file = None
    if cases:
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
            scores[test_result.name] = {m.name: m.score for m in metrics_data}
            reasons[test_result.name] = {m.name: m.reason for m in metrics_data if m.reason}
            cost += sum(m.evaluation_cost or 0 for m in metrics_data)
        # DeepEval doesn't return the file it wrote, so take the newest.
        run_file = max(RESULTS.glob("test_run_*.json"), key=lambda p: p.stat().st_mtime).name

    questions = question_rows(goldens, generated, scores, metric_names)
    categories = sorted({q["category"] for q in questions})
    means = {
        "overall": mean_scores([q["scores"] for q in questions], metric_names),
        **{
            category: mean_scores(
                [q["scores"] for q in questions if q["category"] == category],
                metric_names,
            )
            for category in categories
        },
    }
    non_answers = [
        q["question_id"] for q in questions if q["response_type"] not in (None, "answer")
    ]
    errors = [q["question_id"] for q in questions if q["error"]]
    tokens = total_tokens(questions)

    summary_path = RESULTS / f"summary_{started:%Y%m%d_%H%M%S}.json"
    summary = {
        "run_at": started.isoformat(timespec="seconds"),
        "deepeval_run_file": run_file,
        "judge_cost_usd": round(cost, 4),
        "generator_tokens": tokens,
        "hyperparameters": hyperparameters,
        "non_answers": non_answers,
        "generation_errors": errors,
        "means": means,
        "questions": questions,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    report_path = RESULTS / f"report_{started:%Y%m%d_%H%M%S}.md"
    write_report(report_path, summary, goldens, reasons, metric_names)

    width = max(len(group) for group in means)
    print(f"\n{'':<{width}}  {'  '.join(f'{n:>20}' for n in metric_names)}  questions")
    for group, row in means.items():
        values = "  ".join(f"{row[n]:>20.3f}" for n in metric_names)
        print(f"{group:<{width}}  {values}  {row['questions']:>9}")
    print(f"\nReplies that weren't an Answer (scored 0): {len(non_answers)}")
    print(f"Generation errors (scored 0): {len(errors)}")
    print(f"Generator tokens: {tokens}")
    print(f"Judge cost: ${cost:.2f}")
    print(f"Wrote {summary_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
