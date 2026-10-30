# Running the evals

An **eval** measures how *good* HR Assist's answers are. It asks real questions, using the real index and models, and a second AI model (the **judge**) scores each result from 0 to 1. The pytest tests are different: they use fakes and check that the code works.

The decisions behind the evals are in [ADR 0006](adr/0006-evals-with-deepeval-in-stages.md). When you add an eval, add it to this guide in the same PR.

**Contents:** [The evals](#the-evals) · [Metrics](#metrics) · [Setup](#setup) · [Running an eval](#running-an-eval) · [Reading the results](#reading-the-results) · [Comparing setups](#comparing-setups) · [Building the goldens](#building-the-goldens) · [Troubleshooting](#troubleshooting)

## The evals

Each eval tests one level of the system. Faking a part of the system tells you where a low score comes from.

| Eval | What it tests | Real | Faked | Questions | Judge cost of a full run |
| --- | --- | --- | --- | --- | --- |
| **Retriever** | Search only | Retriever, index | No answer is generated | 89 | ~$0.20 |
| **Generation** | Answers, given the right evidence | Answerer, chat model | Retriever returns the gold chunks | 89 | ~$0.20 |
| **Pipeline** | Search and answers together, as an Employee gets them | Retriever, index, Answerer, chat model | Nothing | 109 | ~$0.65 (estimated from smoke runs) |
| **Application** | The running API over HTTP, judged against the expected answers | The API and everything behind it | Nothing | 45, plus 7 conversations | ~$0.06 (estimated from smoke runs) |

- **The 89 questions** are the ones that should get a normal Answer. All three evals use the same 89, so a question can be followed level by level.
- **The pipeline adds 20 more:** 7 that should get a Clarification, 8 an Abstention and 5 a Refusal.
- **Left out everywhere:** version-and-date questions, which can't be answered while retrieval searches only current documents ([ADR 0007](adr/0007-search-only-current-documents.md)).
- **Questions about an injected test document** that isn't in the index are left out of the first three evals. The application eval sends them, with expected answers rewritten so they don't name that document.
- **Evals run by hand, never in CI.** They cost money and their scores vary a little between runs.

## Metrics

| Metric | Eval | Question it answers | Judge? |
| --- | --- | --- | --- |
| **Contextual Recall** | Retriever, pipeline | Do the retrieved chunks contain *everything* the correct answer needs? | Yes |
| **Contextual Relevancy** | Pipeline | What share of the retrieved text is about the question? Low when the chunks carry a lot of unrelated text | Yes |
| **Contextual Precision** | Retriever | Are the useful chunks ranked *above* the unhelpful ones? | Yes |
| **Faithfulness** | Generation, pipeline | Is every claim in the reply supported by the chunks the model was given? | Yes |
| **Answer Relevancy** | Generation, pipeline | Is every statement in the reply about the question? | Yes |
| **Citation Faithfulness** | Pipeline | Does each `[n]` marker point to a source that supports its claim? Pass (1) or fail (0) per reply | Yes |
| **Citation Precision** | Pipeline | What share of the cited sources are gold sections? | No |
| **Citation Recall** | Pipeline | What share of the gold sections were cited? Citing one of two required sources scores 0.5 | No |
| **Response Type Match** | Pipeline, application | Was the reply the expected kind: Answer, Clarification, Abstention or Refusal? | No |
| **Correctness** | Application | Does anything in the reply contradict the expected answer? Missing points don't count here | Yes (G-Eval) |
| **Completeness** | Application | Does the reply cover every key point of the expected answer? Extra points don't count here | Yes (G-Eval) |
| **Style** | Application | Does the reply follow the prompt's style rules: direct answer first, short and plain, lists for more than two items? | Yes (G-Eval) |

**An example.** Take the question "How many days of annual leave does a new full-time employee get?" (correct answer: 27 days plus 8 bank holidays).
- **Recall** is high if the leave table is among the retrieved chunks.
- **Precision** is high if that table is chunk 1 rather than chunk 5.
- **Citation Recall** is 1 only if the reply cites both documents that hold the table.

Up to the pipeline, none of the judged metrics compares the reply with the correct answer: a reply can be faithful and relevant but incomplete. The reports show the expected answer next to each reply, so you can compare them yourself. The application eval's Correctness and Completeness do compare them.

## Setup

You need:

- the backend set up as in the [README](../README.md), with a `.env` file at the repo root;
- an `OPENAI_API_KEY` in `.env` that can use `gpt-5.6-luna`, the judge;
- for the retriever and pipeline evals, **the dev collection ingested**. If you're not sure it is, run `uv run hr-assist ingest` from `backend/` (about a minute, almost free).

DeepEval is in the `evals` dependency group, and `--group evals` installs it the first time you run a command.

**Whatever is in `.env` is what gets measured.** The evals read the same settings as the app. See [Comparing setups](#comparing-setups) before a run you'll use to make a decision.

## Running an eval

Run every command from the **repo root**, not from `backend/`.

| Eval | Command |
| --- | --- |
| Retriever | `uv run --project backend --group evals python evals/retrieval/run_eval.py` |
| Generation | `uv run --project backend --group evals python evals/generation/run_eval.py` |
| Pipeline | `uv run --project backend --group evals python evals/pipeline/run_eval.py` |
| Application | `uv run --project backend --group evals python evals/application/run_eval.py` |

**The application eval needs the API running.**
- **Start it** as in the [README](../README.md): `uv run uvicorn hr_assist.api.app:create_app --factory` from `backend/`. Restart it after any code or `.env` change.
- **The target.** The runner tests `http://localhost:8000` unless you pass `--base-url`.
- **Pace and quota.** It sends at most `RATE_LIMIT_PER_MINUTE` chats a minute (20), so a full run takes about 3 minutes. It uses 52 of the 100 chats an IP may send per day.
- **Recorded settings.** The API doesn't report its settings, so the summary records the ones in your `.env`. They describe the server only if it runs the same `.env` and code.
- **Smoke test.** `--limit 2` runs 2 questions and 2 conversations.

The steps are the same for each eval:

1. **Smoke test.** Add `--limit 3` to run only the first 3 questions. It costs about $0.01 and checks that everything is connected. Then delete its files from `evals/results/<eval>/`, so nobody mistakes it for a real run.
2. **Full run.** Run the command without `--limit`. When it finishes, it prints a table of scores, the judge cost and the paths of the files it wrote.
3. **Commit the results.** Commit every file the run wrote, so later runs have something to compare against.

To try a different judge, add `--judge-model <model>`, or set `EVAL_JUDGE_MODEL` in `.env`. Scores from different judges can't be compared, so do this only on purpose.

## Reading the results

### The files

Each run writes these files to `evals/results/<eval>/`. All the names include the date and time of the run.

| File | Contents | Use it to |
| --- | --- | --- |
| `report_*.md` | The settings, the score tables, then every question, lowest score first: the expected answer, the reply, the judge's reasons, the chunks and citations | **Start here** |
| `summary_*.json` | Every setting used, the judge cost, mean scores overall and by category, and each question's scores | Compare runs |
| `test_run_*.json` | DeepEval's full record: every verdict, and the full text of every chunk. The pipeline writes two of these, one for the triad and Contextual Relevancy, one for Citation Faithfulness; the application eval writes one for the questions and one for the conversations | Read a chunk's full text |

To read a report in VS Code, open it and press **Cmd+Shift+V** (Ctrl+Shift+V on Windows and Linux). GitHub shows it formatted too. Click a question to expand it.

DeepEval's own viewers don't fit these runs. `deepeval inspect` needs traces, which these runs don't record. `deepeval view` uploads the results to Confident AI, and we keep results local.

### Looking into a low score

Open the report: the problems are at the top. A low score usually has one of these causes:

| What you see | Likely cause | Where to look |
| --- | --- | --- |
| Low Contextual Recall | Search didn't find the right chunk | Chunking, embeddings, `RETRIEVAL_K` |
| Low Contextual Precision only | The right chunk was found but ranked low | Embeddings, a reranker |
| Low Contextual Relevancy with good recall | The right text was found, among a lot of unrelated text | `RETRIEVAL_K`, chunk size, the threshold |
| Low Faithfulness with good recall | The model said more than its sources | Prompt, chat model |
| Low Citation Recall with good recall | The model had the source but didn't cite it | Prompt |
| A wrong Response Type | The model clarified, abstained or refused when it shouldn't have, or the other way round | Prompt rules for each Response Type |
| Low Correctness that names a true extra detail | The application judge sees only the expected answer, not the sources, so it can't verify details beyond it | Check the detail against the policy; Faithfulness at the pipeline level covers grounding |
| A reason that doesn't fit the reply | The judge got it wrong. It happens. Note it: the judge is meant to be checked against a hand-labelled sample | |

### Questions that score 0 without the judge

The summary lists these questions separately. They still count in the means.

| List | Meaning |
| --- | --- |
| `empty_retrievals` | No chunk passed `RETRIEVAL_SCORE_THRESHOLD`, so the app abstained. A long list means the threshold may be too strict |
| `non_answers` | A question that should get an Answer got a Clarification, an Abstention or a Refusal. It isn't judged, because Faithfulness would rate a reply with no claims highly |
| `generation_errors` | The chat model couldn't be reached, or its reply couldn't be read |
| `request_errors` | Application eval only: the API returned an error, or a reply that doesn't match `ChatResponse`. The report shows the status and body |

### Don't over-read small differences

- **A point or two is noise.** Each question is about 1% of the overall score, and the judge can score the same setup slightly differently on two runs.
- **Category scores rest on only 11 to 14 questions.** Use them to find weak spots, not as measurements.

## Comparing setups

### What you can change

Set these in `.env`.

| Setting | Default | Affects | What it does |
| --- | --- | --- | --- |
| `CHUNKING_VERSION` | `chunking_v2` | Retriever, pipeline | How documents are split: `chunking_v1` or `chunking_v2` |
| `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS` | The version's own | Retriever, pipeline | Chunk size, and how much text neighbouring chunks share |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Retriever, pipeline | The model that turns text into vectors for search |
| `RETRIEVAL_K` | `3` | Retriever, pipeline | How many chunks come back for each question |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.65` | Retriever, pipeline | The lowest relevance a chunk needs. `0` turns it off |
| `CHAT_MODEL`, `REASONING_EFFORT`, `MAX_OUTPUT_TOKENS` | See `settings.py` | Generation, pipeline | The model that writes the answers |
| `APP_ENV` | Required | Retriever, pipeline | Picks which index is searched. Keep `development` for evals |
| `EVAL_JUDGE_MODEL` | `gpt-5.6-luna` | All | The judge. Used by the evals only, never by the app |

The prompt (`answering/prompt.py`) and the metrics aren't settings: change them in code. Every setting is described in the [developer guide, section 4.2](developer-guide.md#42-every-setting).

### Change `.env`, not `settings.py`

**Production has no `.env`.** It uses the defaults in `settings.py`, apart from the few values the [deploy workflow](../.github/workflows/deploy.yml) sets. So a change to `settings.py` goes live on the next deploy. Change it only once an eval has shown a value is better, in a PR, with the two summaries as evidence.

> **To measure production, your `.env` must match it.** For example, if your `.env` sets `RETRIEVAL_K=5`, the eval measures 5, while production uses the default of 3.

### Do I need to re-ingest?

| You change | Re-ingest? |
| --- | --- |
| `RETRIEVAL_K`, `RETRIEVAL_SCORE_THRESHOLD`, chat settings | No |
| `CHUNKING_VERSION`, `EMBEDDING_MODEL` | Once per value. Each gets its own collection (for example `development-chunking_v1-text-embedding-3-small`), so afterwards switching is only a `.env` change |
| `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS` | Every time. **Careful:** the collection name doesn't include the sizes, so re-ingesting overwrites the current collection |

### The steps

1. Run the eval on the current setup.
2. Change **one** setting in `.env`, so you know what caused any difference.
3. Re-ingest if the table above says so, then run the eval again.
4. Compare the `means` in the two summaries: overall first, then each category.
5. Set `.env` back to the setup the app should use, because your local app reads it too.

**Two runs are comparable only if** their summaries' `hyperparameters` show the same `judge_model` and `goldens_sha256`. Runs from before [ADR 0007](adr/0007-search-only-current-documents.md) also searched superseded documents, so they aren't comparable with later runs either. The chunk sizes in a summary are read from `.env` at run time, not from the collection.

For example, to compare chunking versions ([ADR 0005](adr/0005-split-oversized-sections-at-unnumbered-headings.md)):

```bash
# CHUNKING_VERSION=chunking_v1 in .env
cd backend && uv run hr-assist ingest && cd ..
uv run --project backend --group evals python evals/retrieval/run_eval.py
# CHUNKING_VERSION=chunking_v2 in .env (usually ingested already)
uv run --project backend --group evals python evals/retrieval/run_eval.py
```

## Building the goldens

A **golden** is one test question with its correct answer and supporting evidence. Every golden file is built by a script from one source file, `evals/eval_questions.json` (125 questions, each with a gold answer and supporting passages). **Never edit a golden file by hand.**

| Golden file | Script | Adds to each question | Rebuild when |
| --- | --- | --- | --- |
| `evals/retrieval/goldens_v1.jsonl` | `python evals/retrieval/build_goldens.py` | Nothing: the question list itself | The questions change |
| `evals/generation/goldens_v1.jsonl` | `uv run --project backend python evals/generation/build_goldens.py` | The gold chunks, rebuilt from `data/` as ingestion does (~25 seconds, free) | The questions, ingestion or chunking change |
| `evals/pipeline/goldens_v1.jsonl` | `uv run --project backend python evals/pipeline/build_goldens.py` | The expected Response Type and the gold sections to cite | The questions or the manifest change |
| `evals/application/goldens_v1.jsonl` and `conversations_v1.jsonl` | `uv run --project backend python evals/application/build_goldens.py` | A 45-question sample of the pipeline goldens, plus 7 Clarification follow-up conversations | The pipeline goldens or either hand-written file change |

- **Build the retriever goldens first.** The generation and pipeline scripts read their question list from them, and the application script reads the pipeline goldens.
- **Read each script's output.** It prints counts, plus any passage that has no chunk or can't be cited (today only `NDS-EVAL-082`'s superseded "Superseded notice").
- **Commit each `.jsonl` file with its pretty-printed `.json` copy.** The evals load only the `.jsonl` file, and the copy is for reading. If the questions didn't change, the retriever goldens must not change either.
- **The scripts stop with an error** on duplicate question IDs, unknown Document IDs, a missing gold answer or passages, or a section sign in the source file. Write "section 6.1".
- **New question set, new file.** When you add or remove questions, write `goldens_v2.jsonl` rather than overwriting v1, because scores from different question sets aren't comparable. Update `OUTPUT` in the build script and `GOLDENS` in the runner.
- **Another chunking version, also a new file.** For example: `build_goldens.py --chunking chunking_v1 --output evals/generation/goldens_chunking_v1.jsonl`.

How the gold chunks and gold sections are found is described in [ADR 0006](adr/0006-evals-with-deepeval-in-stages.md#generation-golden-data).

### Application goldens

Build them after the pipeline goldens, from the repo root:

```bash
uv run --project backend python evals/application/build_goldens.py
```

The script writes two files, each with a `.json` copy for reading:

- **`goldens_v1.jsonl`**: 45 single questions.
  - 3 Answer questions per category, hardest first.
  - Every Clarification, Abstention and Refusal question.
  - The 4 questions about an injected memo.
- **`conversations_v1.jsonl`**: 7 three-turn conversations.
  1. A vague question.
  2. HR Assist's Clarification.
  3. The Employee's reply.

  The judge scores HR Assist's next reply against the expected Answer.

It prints the chosen question IDs for each group.

Two hand-written source files in `evals/application/` feed it. Edit these, never the goldens, and rebuild:

| File | Holds | Why it's hand-written |
| --- | --- | --- |
| `expected_output_overrides.json` | The expected output for each injected-memo question (112, 114, 115, 117), with the reason | Their gold answers name a test document that isn't in the index, so the app can't repeat that part |
| `clarification_follow_ups.json` | For each Clarification question, the Employee's reply, the expected Answer and its sources | `eval_questions.json` has the vague questions but no replies or answers to them |

The script stops with an error when:
- an override still mentions the test document;
- a follow-up is missing for a Clarification question;
- a follow-up cites a section that isn't in a current document;
- the number of questions in a group changes.

Why each choice was made is in [ADR 0006](adr/0006-evals-with-deepeval-in-stages.md#application-golden-data).

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `Collection ... doesn't exist; ingest first` | Run `uv run hr-assist ingest` from `backend/` with the same `.env` |
| `ValidationError` for `Settings` | Copy `.env.example` to `.env` and fill it in |
| `No module named 'deepeval'` | Keep `--group evals` in the command |
| `can't open file '.../run_eval.py'` | Run from the repo root, not `backend/` |
| `'temperature' does not support 0.0 with this model` | DeepEval doesn't know that judge model. Use `gpt-5.6-luna` |
| An OpenAI rate limit or authentication error | Check that the key can use the chat and judge models, then rerun |
| Every question listed under `empty_retrievals` | The collection is empty or the threshold too high: re-ingest, and check `RETRIEVAL_SCORE_THRESHOLD` |
| Pipeline: many `non_answers` | The model is clarifying or abstaining too often. Read those replies in the report before blaming retrieval |
