"""Run the application eval: the running API over HTTP, over the application goldens.

Start the API first (see README), then run from the repo root:
    uv run --project backend --group evals python evals/application/run_eval.py

Sends each golden question, and each Clarification follow-up conversation, to POST /api/chat,
paced under the API's per-minute rate limit. The judge model scores every reply with three G-Eval
metrics, Correctness, Completeness and Style, using fixed evaluation steps and score bands;
whether the Response Type is the expected one is worked out without it. Writes to
evals/results/application/: DeepEval's two test_run_*.json files, one for the questions and one
for the conversations; a summary_*.json with each reply, the scores and the settings the run used;
and a report_*.md that shows the same results for reading. See ADR 0006.
"""

# ruff: noqa: E402  (the environment must be set before deepeval is imported)

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

# DeepEval copies the working directory's .env into the process environment on import, which
# would switch on LangSmith tracing. Settings reads .env itself, so turn that off.
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")

import httpx
from deepeval import evaluate
from deepeval.dataset import ConversationalGolden, Golden
from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig
from deepeval.metrics import ConversationalGEval, GEval
from deepeval.metrics.base_metric import BaseConversationalMetric, BaseMetric
from deepeval.metrics.g_eval.utils import Rubric
from deepeval.models import OpenAIModel
from deepeval.test_case import (
    ConversationalTestCase,
    LLMTestCase,
    MultiTurnParams,
    SingleTurnParams,
    Turn,
)
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from hr_assist.answering.models import ChatResponse
from hr_assist.answering.prompt import PROMPT_VERSION
from hr_assist.settings import REPO_ROOT, REPO_ROOT_ENV_FILE, Settings

HERE = Path(__file__).resolve().parent
GOLDENS = HERE / "goldens_v1.jsonl"
CONVERSATIONS = HERE / "conversations_v1.jsonl"
RESULTS = REPO_ROOT / "evals" / "results" / "application"
CONCURRENT_REQUESTS = 4
REQUEST_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 3
# A source marker such as [2] or [1, 3], with the space before it. The judge reads the reply
# without them; answerer.py has the same pattern.
SOURCE_MARKER = re.compile(r"\s?\[\d+(?:\s*,\s*\d+)*\]")

CORRECTNESS = "Correctness"
COMPLETENESS = "Completeness"
STYLE = "Style"
RESPONSE_TYPE_MATCH = "Response Type Match"
JUDGED = [CORRECTNESS, COMPLETENESS, STYLE]
# Changing a metric's steps or bands changes its scores, so bump this and compare runs only
# within one version.
METRICS_VERSION = "v1"

CORRECTNESS_STEPS = [
    "Read 'expected output', the correct reply, and note what kind of reply it is: an answer, "
    "a clarifying question, a refusal, or a statement that the policies don't cover the question.",
    "If 'expected output' is a clarifying question, 'actual output' is correct only if it asks "
    "for the same missing information, or answers correctly for every reading of the question.",
    "If 'expected output' declines, by refusing or by saying the policies don't cover the "
    "question, 'actual output' must also decline and must not give the information asked for.",
    "Otherwise, list every figure, date, limit, condition and named approver in 'actual output' "
    "and check each against 'expected output'. Figures and units must match exactly.",
    "Count as an error any statement that contradicts 'expected output', or that presents a "
    "superseded or false rule as current.",
    "Don't penalise wording, or extra details that 'expected output' doesn't mention, unless "
    "they contradict it.",
    "Don't penalise points of 'expected output' that 'actual output' leaves out; completeness is "
    "scored separately.",
]
CORRECTNESS_RUBRIC = [
    Rubric(
        score_range=(0, 2),
        expected_outcome="The wrong kind of reply, or it contradicts the expected output on the "
        "main point.",
    ),
    Rubric(
        score_range=(3, 5),
        expected_outcome="The main point is right, but a figure, condition or approver is wrong.",
    ),
    Rubric(
        score_range=(6, 8),
        expected_outcome="Nothing important is wrong; a minor detail is wrong or imprecise.",
    ),
    Rubric(score_range=(9, 10), expected_outcome="Nothing contradicts the expected output."),
]

COMPLETENESS_STEPS = [
    "Split 'expected output' into its key points: each figure, condition, exception and required "
    "approval, or, for a clarifying question, each piece of missing information it asks for, or, "
    "for a refusal, the reason given.",
    "For each key point, check whether 'actual output' states it or an equivalent, in any wording.",
    "Score by the share of key points covered, weighting the points that directly answer the "
    "question above supporting detail.",
    "Don't penalise extra points, and don't judge whether any point is correct; correctness is "
    "scored separately.",
]
COMPLETENESS_RUBRIC = [
    Rubric(score_range=(0, 2), expected_outcome="Misses the main point."),
    Rubric(
        score_range=(3, 5), expected_outcome="Has the main point but misses several key points."
    ),
    Rubric(score_range=(6, 8), expected_outcome="Misses one key point."),
    Rubric(score_range=(9, 10), expected_outcome="Covers every key point."),
]

# The style rules of answering/prompt.py, as checks.
STYLE_STEPS = [
    "Check that 'actual output' gives the direct answer to 'input', or its clarifying question "
    "or refusal, in its first one or two sentences.",
    "Check that the language is plain and succinct, in short sentences, with no filler, hedging "
    "or repetition.",
    "Check that it doesn't restate the question, and leaves out background the question didn't "
    "ask for.",
    "Check that more than two parallel items, such as conditions, steps or options, are given as "
    "a short bulleted list.",
    "Don't judge whether the content is correct or complete.",
]
STYLE_RUBRIC = [
    Rubric(
        score_range=(0, 2),
        expected_outcome="The direct answer is buried or missing, and the reply is long or padded.",
    ),
    Rubric(
        score_range=(3, 5),
        expected_outcome="The direct answer comes late, or several style rules are broken.",
    ),
    Rubric(score_range=(6, 8), expected_outcome="Follows the style rules with one lapse."),
    Rubric(
        score_range=(9, 10),
        expected_outcome="Direct answer first; short and plain; lists where needed; no restated "
        "question or unasked background.",
    ),
]

# In a conversation, only HR Assist's last turn is judged: its earlier Clarification is fixed in
# the golden. The same steps then read the expected outcome instead of the expected output.
LAST_TURN = (
    "Judge only the last assistant turn, reading it with the earlier turns for context. The "
    "earlier assistant turn is fixed and isn't being judged."
)


def for_conversation(steps: list[str]) -> list[str]:
    reworded = [
        step.replace("'expected output'", "the expected outcome")
        .replace("'actual output'", "the last assistant turn")
        .replace("'input'", "the user's question as clarified by their last turn")
        for step in steps
    ]
    return [LAST_TURN, *reworded]


class EvalSettings(BaseSettings):
    """Eval-only settings. The API never uses the judge, so it isn't in the app's Settings."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    eval_judge_model: str = "gpt-5.6-luna"


class MinuteLimiter:
    """Holds each request until fewer than `per_minute` have been sent in the last minute."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._sent: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                # A second of margin, because the server counts from when a request arrives.
                while self._sent and self._sent[0] <= now - 61:
                    self._sent.popleft()
                if len(self._sent) < self.per_minute:
                    self._sent.append(now)
                    return
                await asyncio.sleep(self._sent[0] + 61 - now)


@dataclass
class Reply:
    """One golden's reply, or the HTTP failure that stopped it."""

    response: ChatResponse | None
    status: int | None = None
    error: str | None = None

    @property
    def text(self) -> str:
        """The reply as the judge reads it, with its source markers removed."""
        return SOURCE_MARKER.sub("", self.response.message) if self.response else ""


async def send(
    client: httpx.AsyncClient,
    limiter: MinuteLimiter,
    messages: list[dict[str, str]],
    as_of_date: str,
) -> Reply:
    body = {"messages": messages, "as_of_date": as_of_date}
    status = None
    for _ in range(MAX_ATTEMPTS):
        await limiter.wait()
        try:
            response = await client.post("/api/chat", json=body)
        except httpx.HTTPError as exc:
            return Reply(None, error=f"{type(exc).__name__}: {exc}")
        status = response.status_code
        if status == 429:
            # Another client used up the quota; wait as long as the API says.
            await asyncio.sleep(int(response.headers.get("retry-after", "60")))
            continue
        if status != 200:
            return Reply(None, status, response.text[:500])
        try:
            return Reply(ChatResponse.model_validate_json(response.content), status)
        except ValidationError as exc:
            return Reply(None, status, f"Response doesn't match ChatResponse: {exc}")
    return Reply(None, status, f"Still rate limited after {MAX_ATTEMPTS} attempts")


async def ask_all(
    base_url: str,
    per_minute: int,
    goldens: list[Golden],
    conversations: list[ConversationalGolden],
) -> tuple[list[Reply], list[Reply]]:
    limiter = MinuteLimiter(per_minute)
    limit = asyncio.Semaphore(CONCURRENT_REQUESTS)
    async with httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        health = await client.get("/api/health")
        if health.status_code != 200 or health.json().get("status") != "ok":
            raise SystemExit(f"{base_url}/api/health isn't ok: {health.status_code} {health.text}")

        async def ask(messages: list[dict[str, str]], as_of_date: str) -> Reply:
            async with limit:
                return await send(client, limiter, messages, as_of_date)

        questions = [
            ask(
                [{"role": "user", "content": g.input}],
                g.additional_metadata["as_of_date"],
            )
            for g in goldens
        ]
        follow_ups = [
            ask(
                [{"role": t.role, "content": t.content} for t in c.turns],
                c.additional_metadata["as_of_date"],
            )
            for c in conversations
        ]
        replies = await asyncio.gather(*questions, *follow_ups)
    return replies[: len(goldens)], replies[len(goldens) :]


def question_cases(goldens: list[Golden], replies: list[Reply]) -> list[LLMTestCase]:
    """Every reply the API gave, whatever its Response Type, markers removed."""
    return [
        LLMTestCase(
            name=golden.additional_metadata["question_id"],
            input=golden.input,
            actual_output=reply.text,
            expected_output=golden.expected_output,
            metadata=golden.additional_metadata,
        )
        for golden, reply in zip(goldens, replies, strict=True)
        if reply.response
    ]


def conversation_cases(
    conversations: list[ConversationalGolden], replies: list[Reply]
) -> list[ConversationalTestCase]:
    """Each conversation with the API's reply as its last turn, markers removed."""
    return [
        ConversationalTestCase(
            name=conversation.additional_metadata["question_id"],
            turns=[
                *(Turn(role=t.role, content=t.content) for t in conversation.turns),
                Turn(role="assistant", content=reply.text),
            ],
            scenario=conversation.scenario,
            expected_outcome=conversation.expected_outcome,
            metadata=conversation.additional_metadata,
        )
        for conversation, reply in zip(conversations, replies, strict=True)
        if reply.response
    ]


@dataclass
class Judged:
    scores: dict[str, dict[str, float]] = field(default_factory=dict)
    reasons: dict[str, dict[str, str]] = field(default_factory=dict)
    cost: float = 0.0
    run_files: list[str] = field(default_factory=list)


def judge_cases(
    cases: list[LLMTestCase] | list[ConversationalTestCase],
    metrics: list[BaseMetric] | list[BaseConversationalMetric],
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
        # G-Eval names its metrics "Correctness [GEval]"; keep the plain name.
        judged.scores.setdefault(test_result.name, {}).update(
            {m.name.split(" [")[0]: m.score for m in metrics_data}
        )
        judged.reasons.setdefault(test_result.name, {}).update(
            {m.name.split(" [")[0]: m.reason for m in metrics_data if m.reason}
        )
        judged.cost += sum(m.evaluation_cost or 0 for m in metrics_data)
    # DeepEval doesn't return the file it wrote, so take the newest.
    judged.run_files.append(
        max(RESULTS.glob("test_run_*.json"), key=lambda p: p.stat().st_mtime).name
    )


def rows_for(
    goldens: list[Golden] | list[ConversationalGolden],
    replies: list[Reply],
    judged: Judged,
    kind: str,
) -> list[dict[str, Any]]:
    """Each golden's reply and scores. A failed request scores 0 on every metric."""
    rows = []
    for golden, reply in zip(goldens, replies, strict=True):
        meta = golden.additional_metadata
        question_id = meta["question_id"]
        response_type = reply.response.response_type if reply.response else None
        scores = dict.fromkeys(JUDGED, 0.0) | judged.scores.get(question_id, {})
        scores[RESPONSE_TYPE_MATCH] = float(response_type == meta["expected_response_type"])
        rows.append(
            {
                "question_id": question_id,
                "kind": kind,
                "group": meta.get("selection_group", "follow_up"),
                "category": meta["category"],
                "expected_response_type": meta["expected_response_type"],
                "response_type": response_type,
                "message": reply.response.message if reply.response else None,
                "citations": [
                    f"{c.document_id} {f'slide {c.slide}' if c.slide else c.section}"
                    for c in (reply.response.citations if reply.response else [])
                ],
                "status": reply.status,
                "error": reply.error,
                "scores": scores,
            }
        )
    return rows


def mean_scores(rows: list[dict[str, Any]]) -> dict[str, float]:
    names = [*JUDGED, RESPONSE_TYPE_MATCH]
    return {
        "questions": len(rows),
        **{name: round(fmean(row["scores"][name] for row in rows), 4) for name in names},
    }


def score_table(means: dict[str, dict[str, float]]) -> list[str]:
    names = [*JUDGED, RESPONSE_TYPE_MATCH]
    return [
        f"| | {' | '.join(names)} | Questions |",
        f"|---|{'---|' * len(names)}---|",
        *[
            f"| {group} | {' | '.join(f'{row[n]:.3f}' for n in names)} | {row['questions']} |"
            for group, row in means.items()
        ],
    ]


def write_report(
    path: Path,
    summary: dict[str, Any],
    expected: dict[str, str],
    asked: dict[str, list[dict[str, str]]],
    reasons: dict[str, dict[str, str]],
) -> None:
    """The run's results as Markdown, for VS Code's preview or GitHub. Lowest scores first."""
    settings = summary["hyperparameters"]
    lines = [
        f"# Application eval, {summary['run_at']}",
        "",
        f"`{settings['base_url']}` · `{settings['chat_model']}` (reasoning "
        f"{settings['reasoning_effort']}) · prompt {settings['prompt_version']} · "
        f"judge `{settings['judge_model']}` · metrics {settings['metrics_version']} · "
        f"{settings['goldens_used']} questions and {settings['conversations_used']} conversations "
        f"· judge cost ${summary['judge_cost_usd']:.2f}",
        "",
        "<details><summary>All settings</summary>",
        "",
        *[f"- `{name}`: `{value}`" for name, value in settings.items()],
        f"- DeepEval run files: {', '.join(f'`{f}`' for f in summary['deepeval_run_files'])}",
        "",
        "</details>",
        "",
        "## Scores",
        "",
        *score_table(summary["means"]),
        "",
        f"Failed requests (scored 0): {len(summary['request_errors'])}"
        + (f": {', '.join(summary['request_errors'])}" if summary["request_errors"] else ""),
        "",
        "## Questions and conversations, lowest score first",
        "",
    ]
    for row in sorted(summary["questions"], key=lambda r: min(r["scores"].values())):
        question_id = row["question_id"]
        scores = " · ".join(f"{n} {s:.2f}" for n, s in row["scores"].items())
        lines += [
            f"<details><summary><b>{question_id}</b> · {row['group']} · "
            f"{row['response_type'] or 'error'} (expected {row['expected_response_type']}) · "
            f"{scores}</summary>",
            "",
        ]
        for turn in asked[question_id]:
            lines += [f"**{turn['role'].capitalize()}.** {turn['content']}", ""]
        lines += [f"**Expected.** {expected[question_id]}", ""]
        if row["error"]:
            lines += [f"**Error ({row['status']}).** {row['error']}", ""]
        else:
            lines += [
                f"**Reply ({row['response_type']}).**",
                "",
                *[f"> {line}" for line in row["message"].splitlines()],
                "",
            ]
            if row["citations"]:
                lines += [f"**Citations.** {'; '.join(row['citations'])}", ""]
        for name, reason in reasons.get(question_id, {}).items():
            lines += [f"**{name} {row['scores'][name]:.2f}.** {reason}", ""]
        lines += ["</details>", ""]
    lines.append(
        "The judge's full verdicts are in "
        f"{', '.join(f'`{f}`' for f in summary['deepeval_run_files'])}."
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the application eval (ADR 0006).")
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="The API to test (default local)"
    )
    parser.add_argument("--judge-model", help="Overrides EVAL_JUDGE_MODEL (default gpt-5.6-luna)")
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N questions and N conversations, as a cheap smoke test",
    )
    args = parser.parse_args()

    settings = Settings()
    judge_model = args.judge_model or EvalSettings().eval_judge_model
    goldens = [Golden(**json.loads(line)) for line in GOLDENS.read_text().splitlines()]
    conversations = [
        ConversationalGolden(**json.loads(line)) for line in CONVERSATIONS.read_text().splitlines()
    ]
    goldens, conversations = goldens[: args.limit], conversations[: args.limit]
    # The API doesn't report its settings, so these come from the local .env. They describe the
    # server only when it was started from the same .env and code.
    hyperparameters: dict[str, str | int | float] = {
        "base_url": args.base_url,
        "chat_model": settings.chat_model,
        "reasoning_effort": settings.reasoning_effort,
        "max_output_tokens": settings.max_output_tokens,
        "prompt_version": PROMPT_VERSION,
        "chunking_version": settings.chunking_version,
        "embedding_model": settings.embedding_model,
        "retrieval_k": settings.retrieval_k,
        "retrieval_score_threshold": settings.retrieval_score_threshold,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "judge_model": judge_model,
        "metrics_version": METRICS_VERSION,
        "goldens_file": GOLDENS.name,
        "goldens_sha256": hashlib.sha256(GOLDENS.read_bytes()).hexdigest(),
        "goldens_used": len(goldens),
        "conversations_file": CONVERSATIONS.name,
        "conversations_sha256": hashlib.sha256(CONVERSATIONS.read_bytes()).hexdigest(),
        "conversations_used": len(conversations),
    }

    started = datetime.now(UTC)
    question_replies, follow_up_replies = asyncio.run(
        ask_all(args.base_url, settings.rate_limit_per_minute, goldens, conversations)
    )

    judge = OpenAIModel(model=judge_model, api_key=settings.openai_api_key.get_secret_value())
    # Only scores are recorded. evaluate() refuses metrics without a threshold, so 0 makes every
    # case pass. Fixed steps and bands, rather than criteria the judge turns into new steps each
    # run, keep scores comparable; the judge gives no logprobs to smooth them.
    single = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]
    question_metrics = [
        GEval(
            name=CORRECTNESS,
            evaluation_params=[*single, SingleTurnParams.EXPECTED_OUTPUT],
            evaluation_steps=CORRECTNESS_STEPS,
            rubric=CORRECTNESS_RUBRIC,
            model=judge,
            threshold=0,
        ),
        GEval(
            name=COMPLETENESS,
            evaluation_params=[*single, SingleTurnParams.EXPECTED_OUTPUT],
            evaluation_steps=COMPLETENESS_STEPS,
            rubric=COMPLETENESS_RUBRIC,
            model=judge,
            threshold=0,
        ),
        GEval(
            name=STYLE,
            evaluation_params=single,
            evaluation_steps=STYLE_STEPS,
            rubric=STYLE_RUBRIC,
            model=judge,
            threshold=0,
        ),
    ]
    multi = [MultiTurnParams.ROLE, MultiTurnParams.CONTENT]
    conversation_metrics = [
        ConversationalGEval(
            name=CORRECTNESS,
            evaluation_params=[*multi, MultiTurnParams.EXPECTED_OUTCOME],
            evaluation_steps=for_conversation(CORRECTNESS_STEPS),
            rubric=CORRECTNESS_RUBRIC,
            model=judge,
            threshold=0,
        ),
        ConversationalGEval(
            name=COMPLETENESS,
            evaluation_params=[*multi, MultiTurnParams.EXPECTED_OUTCOME],
            evaluation_steps=for_conversation(COMPLETENESS_STEPS),
            rubric=COMPLETENESS_RUBRIC,
            model=judge,
            threshold=0,
        ),
        ConversationalGEval(
            name=STYLE,
            evaluation_params=multi,
            evaluation_steps=for_conversation(STYLE_STEPS),
            rubric=STYLE_RUBRIC,
            model=judge,
            threshold=0,
        ),
    ]

    RESULTS.mkdir(parents=True, exist_ok=True)
    judged = Judged()
    # Two runs, because DeepEval judges questions and conversations as different test cases.
    judge_cases(
        question_cases(goldens, question_replies), question_metrics, hyperparameters, judged
    )
    judge_cases(
        conversation_cases(conversations, follow_up_replies),
        conversation_metrics,
        hyperparameters,
        judged,
    )

    questions = rows_for(goldens, question_replies, judged, "question")
    follow_ups = rows_for(conversations, follow_up_replies, judged, "conversation")
    rows = questions + follow_ups
    groups = ["answer", "clarification", "abstention", "refusal", "injected_memo", "follow_up"]
    means = {"overall questions": mean_scores(questions)} if questions else {}
    means |= {
        group: mean_scores([r for r in rows if r["group"] == group])
        for group in groups
        if any(r["group"] == group for r in rows)
    }
    errors = [r["question_id"] for r in rows if r["error"]]

    summary_path = RESULTS / f"summary_{started:%Y%m%d_%H%M%S}.json"
    summary = {
        "run_at": started.isoformat(timespec="seconds"),
        "deepeval_run_files": judged.run_files,
        "judge_cost_usd": round(judged.cost, 4),
        "hyperparameters": hyperparameters,
        "request_errors": errors,
        "means": means,
        "questions": rows,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    expected = {g.additional_metadata["question_id"]: g.expected_output for g in goldens} | {
        c.additional_metadata["question_id"]: c.expected_outcome for c in conversations
    }
    asked = {
        g.additional_metadata["question_id"]: [{"role": "user", "content": g.input}]
        for g in goldens
    } | {
        c.additional_metadata["question_id"]: [
            {"role": t.role, "content": t.content} for t in c.turns
        ]
        for c in conversations
    }
    report_path = RESULTS / f"report_{started:%Y%m%d_%H%M%S}.md"
    write_report(report_path, summary, expected, asked, judged.reasons)

    names = [*JUDGED, RESPONSE_TYPE_MATCH]
    width = max(len(name) for name in means)
    print(f"\n{'':<{width}}  {'  '.join(f'{n:>19}' for n in names)}  questions")
    for name, row in means.items():
        values = "  ".join(f"{row[n]:>19.3f}" for n in names)
        print(f"{name:<{width}}  {values}  {row['questions']:>9}")
    print(f"\nFailed requests: {len(errors)}" + (f": {', '.join(errors)}" if errors else ""))
    print(f"Judge cost: ${judged.cost:.2f}")
    print(f"Wrote {summary_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
