---
status: proposed
---

# Evaluate HR Assist with DeepEval, level by level, starting with the retriever

Several decisions are waiting on evidence: whether `chunking_v2` is at least as good as `chunking_v1` ([ADR 0005](0005-split-oversized-sections-at-unnumbered-headings.md)), whether `text-embedding-3-small` misses relevant chunks, and whether two-step RAG needs extra steps such as query rewriting ([ADR 0002](0002-openai-models-and-two-step-rag.md)). Today the only way to judge a change is to try a few questions by hand. We have 125 eval questions with gold answers and supporting passages (`evals/eval_questions.json`), but nothing runs them.

We will build evals with **DeepEval**, using LLM-as-a-judge metrics, at three levels: component, pipeline and application. They will be built **one stage at a time**, and each stage starts by preparing its golden data, so it is clear what is measured and why before any eval code exists. **LangSmith stays for tracing only.** Evals are **run by hand**, and every run writes its results and the settings it used to a file. CI comes after the application-level evals exist.

## Levels

| Level | What is evaluated | Seam in the code | What it answers |
|---|---|---|---|
| Component: chunking | Ingestion output | `ChunkingStrategy`, `build_chunks` | Are sections, tables and headings kept intact? Already covered by pytest in `tests/test_ingestion.py`. |
| Component: retriever | Retrieval only, no generation | `Retriever.retrieve(query, k)` | Do the chunks returned for a question contain what the gold answer needs, and are they ranked first? |
| Component: generation | The Answerer given the gold chunks, not retrieved ones | `Answerer` with a fake `Retriever` | Given the right evidence, does the model stick to it and answer the question asked? Separates model failures from retrieval misses. |
| Pipeline | Retrieval and generation together | `Answerer.answer(ChatRequest)` | The end-to-end answer quality an Employee would get. |
| Application | The running API over HTTP | `POST /api/chat` | Behaviour of the deployed system: response schema, errors, rate limits, latency, Refusals of injection and privacy questions. |

The `Retriever` and `ChatModel` Protocols in `answering/answerer.py` are what make the component levels cheap: either side can be replaced by a fake without touching the other.

## Stages

Each stage is reviewed before the next begins.

1. **Retriever golden data** (done). `evals/retrieval/build_goldens.py` writes `evals/retrieval/goldens_v1.jsonl`. See [Retriever golden data](#retriever-golden-data).
2. **Retriever eval, run by hand.** `evals/retrieval/run_eval.py` scores Contextual Recall and Contextual Precision against the dev collection and writes results per run. See [Retriever eval](#retriever-eval).
3. **Generation golden data and eval.** `evals/generation/build_goldens.py` writes `evals/generation/goldens_v1.jsonl`. See [Generation golden data](#generation-golden-data).
4. **Pipeline golden data and eval.** `evals/pipeline/build_goldens.py` writes `evals/pipeline/goldens_v1.jsonl`, adding the Clarification, Abstention and Refusal questions to the Answer questions. See [Pipeline golden data](#pipeline-golden-data).
5. **Application golden data and eval.** A smaller set sent over HTTP.
6. **CI.** A manually triggered workflow that runs the evals and keeps each run's results.

Metrics, thresholds and data for stages 3 to 5 are decided when each stage starts, and recorded by updating this ADR.

## Retriever golden data

- **Source.** `evals/eval_questions.json`, a pretty-printed JSON array of the 125 questions with their gold answers and supporting passages. It replaced two files that held the same questions: `07_RAG_Evaluation_Questions.csv`, whose columns all repeated in `08_RAG_Evaluation_Gold_Answers.jsonl`. The build fails on duplicate question IDs.
- **Which questions.** Every question whose expected behaviour is `answer`, except two categories:
  - `versioning_temporal` (12): the right chunk depends on the Applicable Date and which Document Version was in force, and retrieval has no date filter yet. They return when it does.
  - `privacy_injection_robustness` (3): they cite `NDS-TEST-INJ-010`, a Test Fixture that isn't in the Corpus. They test the Answerer's resistance to injected content, so they belong to the pipeline level.

  That leaves **89 questions**: factual retrieval 14, numerical calculation 14, conditional eligibility 13, multi-hop 13, cross-document 13, semantic paraphrase 11, table extraction 11. Questions expecting a Clarification, Abstention or Refusal are left out because they have no right context to retrieve.
- **Shape.** Each line is a DeepEval Golden, loadable with `EvaluationDataset.add_goldens_from_jsonl_file`:
  - `input`: the question.
  - `expected_output`: the full `gold_answer` from file 08, not the short `expected_answer`. Contextual Recall splits this into statements, so the fuller answer gives a fairer score.
  - `context`: the verbatim quotes from `supporting_passages`. The retriever metrics don't use it; the generation stage will.
  - `additional_metadata`: question ID, category, difficulty, source Document IDs and source sections, so results can be broken down by category.
- **Checks.** Every cited Document ID must be in `data/manifest.yaml`, and every question must have a gold answer and supporting passages.
- **Normalisation.** The original files wrote sections with the section sign. `eval_questions.json` spells it out as "section 6.1", and the build fails if the sign comes back.
- **Fixed set.** The file is regenerated only by the script, never edited by hand. The script also writes a pretty-printed copy (`goldens_v1.json`) for reading; the evals load only the JSONL file. The generation goldens do the same. A change to which questions are included produces a new version (`goldens_v2.jsonl`), so runs on different sets are never compared by mistake.
- **Standalone.** The script uses only the Python standard library and lives beside the data it produces, outside the backend package. It reads Document IDs from the manifest by pattern match, which is enough to catch an unknown ID.

## Generation golden data

- **Which questions.** The same 89 as the retriever goldens, read from `evals/retrieval/goldens_v1.jsonl`, so the two levels line up question by question. `versioning_temporal` stays out to match; the injection questions go to the pipeline level.
- **Evidence.** Each question's gold chunks are found offline, with no Qdrant or embeddings. The build makes every chunk the way ingestion does (`build_chunks` with the chosen chunking strategy). For each supporting passage, it takes every chunk of the cited Document ID whose section number is the passage's section or one of its subsections ("6.3, Table 6.3" takes section 6.3), or, for a deck, the cited slide. The Document ID is needed because section numbers repeat across documents. The quotes aren't matched: the section rule needs no text comparison, and a whole section gives the model the table headings and conditions a quote leaves out. (The quotes are verbatim in the source, but the PDF parser writes `<br>` where a table cell wraps, so 26 of the 149 don't match chunk text character for character.)
- **No manual step.** When a section spans several chunks, all of them are used. A passage whose section names no chunk is skipped and listed; the build fails only if a question gets no chunks. On `chunking_v2` one passage is skipped: `NDS-EVAL-082`'s "Superseded notice", a banner ingestion strips. Questions get 1 to 6 chunks, most 1 or 2.
- **No dependency on `retrieval_k`.** The gold chunks come from the gold data, and the fake retriever returns them whatever `k` it is asked for. A question whose evidence spans more chunks than `k` gets more here than production gives it; that gap is retrieval's, and the pipeline level measures it.
- **Frozen.** The chunks are stored in the golden, so a prompt or model change is compared on the same input. Each golden records its `chunking_version`; goldens for another strategy are a new version, built with `--chunking`.
- **Shape.** `input`, `expected_output` and `context` as in the retriever goldens. `retrieval_context` holds each gold chunk's full text, header lines included, as the model sees it. `additional_metadata` adds the As-Of Date, `must_mention`, `must_not_claim`, the chunking version, any skipped passages, and the full chunks with metadata for the fake retriever.
- **Metrics.** DeepEval `FaithfulnessMetric` (are the reply's claims supported by the gold chunks?) and `AnswerRelevancyMetric` (does the reply address the question?). Neither uses the gold answer, so a grounded but wrong answer can score well; correctness and citation accuracy come at the pipeline or application level.

## Generation eval

- **Running it.** From the repo root, `uv run --project backend --group evals python evals/generation/run_eval.py`, with `--limit N` for a smoke test and `--judge-model` to override the judge. A 3-question smoke run cost $0.006 in judge tokens with `gpt-5.6-luna`, so a full run is expected to cost about $0.20.
- **What answers.** The real `Answerer` and `OpenAIChatModel`, with the chat model, reasoning effort and output cap from `Settings`, so the eval measures what the app does. A `FixedRetriever` returns the golden's frozen chunks and ignores `k`. Each question is asked on its own, with the golden's As-Of Date.
- **What is judged.** `actual_output` is the reply with its `[n]` source markers removed; `retrieval_context` is the gold chunks as the model sees them. Only replies whose Response Type is Answer are judged.
- **Non-answers score 0.** Every generation golden expects an Answer. A Clarification, Abstention or Refusal isn't sent to the judge: it scores 0 on both metrics and is listed under `non_answers`. Faithfulness would otherwise rate it highly, because it makes no claims. An `UpstreamError` also scores 0 and is listed under `generation_errors`.
- **Every setting is recorded**: chat model, reasoning effort, output cap, prompt version, chunking version of the goldens, judge model, and golden file name, hash and number used. `retrieval_k` isn't, because it has no effect. The summary also holds the generator's token totals and each reply.
- **Results.** The same three files as the retriever eval, under `evals/results/generation/`. The report shows each reply beside the expected answer, because neither metric compares them.
- **No tracing**, as in the retriever eval.

## Pipeline golden data

- **Which questions.** 109 in all:
  - **The 89 Answer questions** of the retriever goldens, read from `evals/retrieval/goldens_v1.jsonl`, so the three levels line up question by question.
  - **20 questions that expect another Response Type:** 7 Clarification (`ambiguous_clarification`), 8 Abstention (`unanswerable_out_of_scope`) and 5 Refusal (`privacy_injection_robustness`: 110, 111, 113, 116, 118).
- **Left out.**
  - `versioning_temporal` stays out, because retrieval searches only current documents ([ADR 0007](0007-search-only-current-documents.md)).
  - Every question citing `NDS-TEST-INJ-010` (112, 114, 115, 117) moves to the application level. The fixture isn't in the Corpus, so the real retriever never returns it.
- **Nothing retrieved at build time.** The pipeline retrieves live with `retrieval_k` and `retrieval_score_threshold` from `Settings` (5 and 0.65 in `.env`). So the golden holds no `retrieval_context` and doesn't depend on a chunking version.
- **Shape.**
  - `input`, `expected_output` (the `gold_answer`, which Contextual Recall needs) and `context`, as in the retriever goldens.
  - `additional_metadata` adds:
    - `expected_response_type`: the eval questions file's `expected_behaviour`, as a Response Type.
    - The As-Of Date, `must_mention` and `must_not_claim`.
    - `citation_targets` and `unreachable_passages`.
- **Citation targets.**
  - **One per supporting passage of an Answer question.** Each is the Document ID with the passage's leading section number ("6.1" from "6.1, Table 6.1") or its slide. The patterns are the same as the generation goldens' section rule.
  - **Unreachable passages.** A passage whose document isn't current, or whose section names neither a number nor a slide, can't be cited. It is listed under `unreachable_passages` and kept out of the targets. Only `NDS-EVAL-082`'s superseded "Superseded notice" is unreachable.
  - **Build checks.** The build fails if an Answer question is left with no target. Questions have 1 to 4 targets, most 1 or 2, which fits within `retrieval_k`.
- **Metrics.**
  - **Answer Relevancy, Faithfulness and Contextual Recall** (the RAG triad), on Answer questions only.
    - Faithfulness and Contextual Recall judge against every retrieved chunk, as the model sees it.
    - `actual_output` has its `[n]` markers removed, as in the generation eval.
    - A reply that isn't an Answer, an empty retrieval or an `UpstreamError` scores 0 and is listed.
  - **Citation precision and recall**, with no judge.
    - A citation hits a target when its `document_id` matches and either its slide matches, or the leading number of its `section` is the target's section or a subsection of it.
    - Precision is the share of citations that hit a target. Recall is the share of targets hit.
    - Recall is strict: it counts every target, so citing only one of two documents that hold the same table scores 0.5, as the questions' citation requirements ask for both.
  - **Citation Faithfulness**, DeepEval's community `CitationFaithfulnessMetric`. It's a judge: pass or fail per Answer, on whether each `[n]` marker points to a source that supports its claim.
    - It doesn't use the gold, so it complements the precision and recall above.
    - The Answerer renumbers markers so `[n]` is the n-th citation, so the metric's `retrieval_context` is the cited chunks in citation order, not the retrieved ones.
  - **Response Type match**, 1 or 0 for every question, with no judge. For the 20 other questions it's their only score. For the 89 Answer questions it's the answer rate.
  - Judge metrics use `threshold=0` and `eval_mode="llm"`, as in the earlier evals.

## Retriever eval

- **Running it.** From the repo root, `uv run --project backend --group evals python evals/retrieval/run_eval.py`. DeepEval is in its own `evals` dependency group, so CI doesn't install it. `--limit N` runs the first N goldens as a cheap smoke test; the summary records how many were used. A full run costs about $0.20 in judge tokens with `gpt-5.6-luna` (it cost about $1.57 with `gpt-6-sol`, the first judge).
- **Metrics.** DeepEval `ContextualRecallMetric` (what share of the gold answer's statements can be attributed to the retrieved chunks) and `ContextualPrecisionMetric` (whether the relevant chunks are ranked above the irrelevant ones). Only scores are recorded. DeepEval's `evaluate()` refuses metrics without a threshold, so both are given `threshold=0` and every case passes; pass and fail mean nothing here. `eval_mode="llm"` is pinned, so `DEEPEVAL_EVAL_MODE` can't hand the decisions to another model.
- **What is retrieved.** The real `QdrantRetriever` against the dev collection (`development-{chunking_version}-{embedding_model}`), with `retrieval_k` and `retrieval_score_threshold` read from `Settings`, so the eval measures what the app does. `retrieval_context` is each chunk's full text, header lines included, as the model sees it.
- **No answer is generated.** Neither metric needs `actual_output`, so it is left unset.
- **Empty retrievals.** When no chunk passes `retrieval_score_threshold`, the question isn't sent to the judge. It scores 0 in the summary and is listed under `empty_retrievals`, not dropped.
- **Every setting is recorded** through `evaluate(hyperparameters=...)` and in the summary: chunking version, chunk size and overlap, embedding model, collection name and its chunk count, `retrieval_k`, `retrieval_score_threshold`, judge model, and golden file name, hash and number used. The git commit isn't recorded for now. The collection doesn't record the chunk size and overlap it was built with, so these are what `Settings` gives, which match the collection only if it was ingested with the same `Settings`.
- **Results.** Each run writes three files under `evals/results/retrieval/`:
  - DeepEval's timestamped `test_run_*.json`, with every verdict and reason and the full text of every retrieved chunk.
  - A `summary_*.json` that names that file and holds the judge cost, the settings, mean scores overall and by category, and each question's scores. Compare runs through the summaries.
  - A `report_*.md` for reading: the same scores, then every question, lowest score first, with its expected answer, the judge's reasons and the start of each retrieved chunk. It renders in VS Code's preview and on GitHub.

  DeepEval's own viewers don't fit. `deepeval inspect` shows only traces, which these runs don't record, and `deepeval view` uploads the run to Confident AI.
- **Environment.** Telemetry is turned off with `DEEPEVAL_TELEMETRY_OPT_OUT=1`. DeepEval copies the working directory's `.env` into the process environment on import, which would switch on LangSmith tracing for eval retrievals, so `DEEPEVAL_DISABLE_DOTENV=1` is set too; `Settings` reads `.env` itself.

### Judge model

The judge is **`gpt-5.6-luna`**, set through `EVAL_JUDGE_MODEL` (in the environment or `.env`, with a `--judge-model` override), not through the app's `Settings`, because the API never uses it. A dated snapshot ID is used when one exists, so the judge can't change between runs; DeepEval 4.3.2 lists none for `gpt-5.6-luna`, so the plain ID is used for now.

The criteria for choosing a judge, most important first:

1. Agreement with human judgement on a small hand-labelled sample (about 15 questions). This is the deciding test.
2. Reading tables, numbers, dates and policy wording accurately.
3. Returning valid structured output reliably, because DeepEval's judge prompts expect JSON.
4. Giving the same score for the same input on repeated runs.
5. A pinned version.
6. Cost per run, which is small at this volume (89 questions, a few judge calls each).
7. Being a different model from the generator, which matters from the generation stage on, where a model tends to favour its own answers.

`gpt-6-luna`, the generator, was not chosen as the judge: it would be judging its own answers from the generation stage on.

**Changed from `gpt-6-sol` on 2026-10-28, for cost.** The first judge was `gpt-6-sol` ($2 input, $10 output per million tokens); a full retriever run cost about $1.57. `gpt-5.6-luna` ($0.20 / $1.20) costs about a tenth: 3-question smoke runs cost $0.005 to $0.006 against $0.047. DeepEval knows it, so it uses OpenAI's structured outputs and the judge's JSON is enforced by the API (criterion 3). The risk is criterion 2: a small model is more likely to miss a detail in a table or a number. That is a prior, not a measurement; the hand-labelled sample (criterion 1) should test it before its scores decide anything close.

Considered: `gpt-6.1-terra` ($1 / $5), newer than `gpt-6-sol` at half its price. DeepEval 4.3.2 doesn't list it, so it sends a temperature the model rejects and doesn't request structured outputs; the runners would have to register its capabilities and prices.

Runs judged by `gpt-6-sol`, including the `chunking_v2` runs behind [ADR 0005](0005-split-oversized-sections-at-unnumbered-headings.md), can't be compared with runs judged by `gpt-5.6-luna`. Compare across the change only by re-running the older setting with the new judge.

## Reading the results

- Each retriever question is about 1.1% of the overall score, so differences of a point or two between runs are noise.
- Per-category scores rest on 11 to 14 questions each. Use them to find weak spots, not as measurements.
- A judge-scored metric can move with no code change. Compare runs only when they used the same judge model and golden file, both of which are in the recorded settings.
- To compare chunking strategies, ingest each into its own collection (the collection name already includes the chunking version) and run the eval against each.
- Better retrieval doesn't guarantee better answers, so a retrieval improvement should be confirmed at the pipeline level once it exists.

## Considered options

- **LangSmith for evals as well as tracing.** It is already installed, `evaluate()` attaches scores to the traces that produced them, and it compares experiments side by side. Rejected in favour of DeepEval's metrics and local results files; the cost is that a low score has to be matched to its trace by hand, for example through the question ID in trace metadata.
- **Ragas.** A metrics library rather than an eval runner, and its API has changed between versions. DeepEval provides the same RAG metrics.
- **Rule-based retrieval metrics (hit@k, MRR, recall@k against the labelled source sections).** Deterministic and free, but they need a parser to match labels like "section 6.1, Table 6.1" to chunk sections, and they need a rule for whether one of several listed sources is enough. The LLM-judged metrics check the gold answer's content instead, which avoids both. Can be added later if judge noise hides real changes.
- **A 50-question sample.** Rejected in favour of all 89 relevant questions, which halves the per-question weight and keeps the per-category counts usable.
- **Running evals on every CI build.** Judge-scored metrics are slow, cost money and vary between runs, so they would make builds flaky. Evals are run by hand until the application level exists.
- **promptfoo** (strong at HTTP and red-team testing, but a Node tool) and **Arize Phoenix** (self-hosted, for when data must not leave our infrastructure). Neither is needed now; promptfoo may be reconsidered for the application level.

## Consequences

- DeepEval becomes a development dependency, and each eval run costs judge tokens.
- Eval results live in files in the repo rather than a hosted dashboard, so comparing runs means comparing files.
- The eval questions file becomes a maintained asset: a change to them means regenerating the goldens and, if the included questions change, a new golden version.
- ADR 0005 was accepted on 2026-10-28, after retriever eval runs showed `chunking_v2` scores at least as well as `chunking_v1`.
