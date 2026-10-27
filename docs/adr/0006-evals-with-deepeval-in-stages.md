---
status: proposed
---

# Evaluate HR Assist with DeepEval, level by level, starting with the retriever

Several decisions are waiting on evidence: whether `chunking_v2` is at least as good as `chunking_v1` ([ADR 0005](0005-split-oversized-sections-at-unnumbered-headings.md)), whether `text-embedding-3-small` misses relevant chunks, and whether two-step RAG needs extra steps such as query rewriting ([ADR 0002](0002-openai-models-and-two-step-rag.md)). Today the only way to judge a change is to try a few questions by hand. We have 125 eval questions (`evals/07_RAG_Evaluation_Questions.csv`) with gold answers and supporting passages (`evals/08_RAG_Evaluation_Gold_Answers.jsonl`), but nothing runs them.

We will build evals with **DeepEval**, using LLM-as-a-judge metrics, at three levels: component, pipeline and application. They will be built **one stage at a time**, and each stage starts by preparing its golden data, so it is clear what is measured and why before any eval code exists. **LangSmith stays for tracing only.** Evals are **run by hand**, and every run writes its results and the settings it used to a file. CI comes after the application-level evals exist.

## Levels

| Level | What is evaluated | Seam in the code | What it answers |
|---|---|---|---|
| Component: chunking | Ingestion output | `ChunkingStrategy`, `build_chunks` | Are sections, tables and headings kept intact? Already covered by pytest in `tests/test_ingestion.py`. |
| Component: retriever | Retrieval only, no generation | `Retriever.retrieve(query, k)` | Do the chunks returned for a question contain what the gold answer needs, and are they ranked first? |
| Component: generation | The Answerer given the gold passages, not retrieved ones | `Answerer` with a fake `Retriever` | Given the right evidence, does the model answer correctly, cite it, and pick the right Response Type? Separates model failures from retrieval misses. |
| Pipeline | Retrieval and generation together | `Answerer.answer(ChatRequest)` | The end-to-end answer quality an Employee would get. |
| Application | The running API over HTTP | `POST /api/chat` | Behaviour of the deployed system: response schema, errors, rate limits, latency, Refusals of injection and privacy questions. |

The `Retriever` and `ChatModel` Protocols in `answering/answerer.py` are what make the component levels cheap: either side can be replaced by a fake without touching the other.

## Stages

Each stage is reviewed before the next begins.

1. **Retriever golden data** (done). `evals/retrieval/build_goldens.py` writes `evals/retrieval/goldens_v1.jsonl`. See [Retriever golden data](#retriever-golden-data).
2. **Retriever eval, run by hand.** Contextual Recall and Contextual Precision against the dev collection, results written per run. See [Retriever eval](#retriever-eval).
3. **Generation golden data and eval.** Reuses the supporting passages already in the retriever goldens' `context` field as the fake retriever's output.
4. **Pipeline golden data and eval.** Adds the questions the retriever level leaves out: Clarification, Abstention and Refusal cases, and the privacy and injection questions.
5. **Application golden data and eval.** A smaller set sent over HTTP.
6. **CI.** A manually triggered workflow that runs the evals and keeps each run's results.

Metrics, thresholds and data for stages 3 to 5 are decided when each stage starts, and recorded by updating this ADR.

## Retriever golden data

- **Source.** The question list comes from file 07, and the gold answer and supporting passages from file 08, joined by `question_id`. The build checks that both files hold the same IDs and agree on question, category, difficulty, expected behaviour, expected answer and source sections, and fails on any difference.
- **Which questions.** Every question whose expected behaviour is `answer`, except two categories:
  - `versioning_temporal` (12): the right chunk depends on the Applicable Date and which Document Version was in force, and retrieval has no date filter yet. They return when it does.
  - `privacy_injection_robustness` (3): they cite `NDS-TEST-INJ-010`, a Test Fixture that isn't in the Corpus. They test the Answerer's resistance to injected content, so they belong to the pipeline level.

  That leaves **89 questions**: factual retrieval 14, numerical calculation 14, conditional eligibility 13, multi-hop 13, cross-document 13, semantic paraphrase 11, table extraction 11. Questions expecting a Clarification, Abstention or Refusal are left out because they have no right context to retrieve.
- **Shape.** Each line is a DeepEval Golden, loadable with `EvaluationDataset.add_goldens_from_jsonl_file`:
  - `input`: the question.
  - `expected_output`: the full `gold_answer` from file 08, not the short `expected_answer` from file 07. Contextual Recall splits this into statements, so the fuller answer gives a fairer score.
  - `context`: the verbatim quotes from `supporting_passages`. The retriever metrics don't use it; the generation stage will.
  - `additional_metadata`: question ID, category, difficulty, source Document IDs and source sections, so results can be broken down by category.
- **Checks.** Every cited Document ID must be in `data/manifest.yaml`, and every question must have a gold answer and supporting passages.
- **Normalisation.** The source files write sections with the section sign; the build spells it out as "section 6.1".
- **Fixed set.** The file is regenerated only by the script, never edited by hand. A change to which questions are included produces a new version (`goldens_v2.jsonl`), so runs on different sets are never compared by mistake.
- **Standalone.** The script uses only the Python standard library and lives beside the data it produces, outside the backend package. It reads Document IDs from the manifest by pattern match, which is enough to catch an unknown ID.

## Retriever eval

- **Metrics.** DeepEval `ContextualRecallMetric` (what share of the gold answer's statements can be attributed to the retrieved chunks) and `ContextualPrecisionMetric` (whether the relevant chunks are ranked above the irrelevant ones). Both are run with `threshold=None`, so they record scores without pass or fail.
- **What is retrieved.** The real retriever against the dev collection (`development-{chunking_version}-{embedding_model}`), with `retrieval_k` and `retrieval_score_threshold` read from `Settings`, so the eval measures what the app does. `retrieval_context` is each chunk's full text, header lines included, as the model sees it.
- **No answer is generated.** Both metrics list `actual_output` as required but don't use it in their scores, so it gets a placeholder.
- **Empty retrievals.** When no chunk passes `retrieval_score_threshold`, the question scores 0 and is counted separately, not dropped.
- **Every setting is recorded** through `evaluate(hyperparameters=...)`: chunking version, chunk size and overlap, embedding model, collection name and its chunk count, `retrieval_k`, `retrieval_score_threshold`, judge model, golden file name and hash, and git commit.
- **Results.** Each run writes a timestamped `test_run_*.json` through DeepEval's results folder setting, under `evals/results/retrieval/`.
- **Telemetry** is turned off with `DEEPEVAL_TELEMETRY_OPT_OUT=1`.

### Judge model

The judge is **`gpt-6-sol`**, set through `EVAL_JUDGE_MODEL` (with a command-line override), not through the app's `Settings`, because the API never uses it. A dated snapshot ID is used when one exists, so the judge can't change between runs.

The criteria for choosing a judge, most important first:

1. Agreement with human judgement on a small hand-labelled sample (about 15 questions). This is the deciding test.
2. Reading tables, numbers, dates and policy wording accurately.
3. Returning valid structured output reliably, because DeepEval's judge prompts expect JSON.
4. Giving the same score for the same input on repeated runs.
5. A pinned version.
6. Cost per run, which is small at this volume (89 questions, a few judge calls each).
7. Being a different model from the generator, which matters from the generation stage on, where a model tends to favour its own answers.

`gpt-6-luna`, the generator, was not chosen as the judge: as the cheapest model it is the most likely to miss detail or break the JSON format, and it would be judging its own answers at later stages. That is a prior, not a measurement; the hand-labelled sample can test it.

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
- The eval data files 07 and 08 become a maintained asset: a change to them means regenerating the goldens and, if the included questions change, a new golden version.
- ADR 0005 can move to accepted once a retriever eval shows `chunking_v2` scores at least as well as `chunking_v1`.
