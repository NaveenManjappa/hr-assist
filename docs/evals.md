# Running the evals

This guide explains how we measure HR Assist's quality, and how to run the evals yourself. You don't need to know anything about evals before you start. [ADR 0006](adr/0006-evals-with-deepeval-in-stages.md) records the decisions behind them.

> **Status:** the **retriever eval** and the **generation eval** exist. The pipeline and application evals are later stages (see [What comes next](#10-what-comes-next)). When you add one, add its section to this guide in the same PR.

## Contents

1. [What an eval is](#1-what-an-eval-is)
2. [Words you'll meet](#2-words-youll-meet)
3. [What the retriever eval checks](#3-what-the-retriever-eval-checks)
4. [Before you start](#4-before-you-start)
5. [How to run the retriever eval](#5-how-to-run-the-retriever-eval)
6. [Reading the results](#6-reading-the-results)
7. [Comparing two setups](#7-comparing-two-setups)
8. [Building the golden files](#8-building-the-golden-files)
9. [How to run the generation eval](#9-how-to-run-the-generation-eval)
10. [What comes next](#10-what-comes-next)
11. [Troubleshooting](#11-troubleshooting)

## 1. What an eval is

An **eval** is a test of how *good* the answers are, not just whether the code works.

The pytest tests check things like "does the API return the right shape?". They use fakes and give the same result every time. An eval is different: it asks HR Assist real questions, using the real index and real models, and gives each result a **score from 0 to 1**.

We have 125 test questions, each with a correct answer written by hand. The evals compare what HR Assist does with those answers.

## 2. Words you'll meet

| Word | Meaning |
| --- | --- |
| **Golden** | One test question, with its correct answer and the policy text that supports it. The goldens file is the answer key. |
| **Retriever** | The part of HR Assist that searches the policy index and returns the most relevant chunks for a question. |
| **Chunk** | A piece of a policy document as stored in the index, usually one numbered section. |
| **Judge model** | A second AI model that reads the results and decides the scores. We use `gpt-5.6-luna`. This is called "LLM-as-a-judge". |
| **DeepEval** | The Python library that runs the judge and works out the scores. |
| **Contextual Recall** | Did the retrieved chunks contain *everything* the correct answer needs? 1.0 means every fact in the correct answer can be found in them. |
| **Contextual Precision** | Were the *useful* chunks ranked at the top, above the unhelpful ones? 1.0 means every useful chunk came first. |

**An example.** The question is "How many days of annual leave does a new full-time employee get?". The correct answer is "27 days plus 8 bank holidays".

- If the retrieved chunks include the leave table, **recall** is high. If they're about sick pay, it's low.
- If the leave table is chunk 1 of 5, **precision** is high. If it's chunk 5, under four unhelpful chunks, precision is lower.

## 3. What the retriever eval checks

It checks **search only**. For each golden it:

1. sends the question to the real retriever, exactly as the app would;
2. collects the chunks that come back;
3. asks the judge to score Contextual Recall and Contextual Precision for those chunks against the correct answer.

**No answer is generated.** This is on purpose: when an answer is wrong, we want to know whether the search failed or the chat model did. This eval looks at the search on its own.

It uses **89 of the 125 questions**: the ones that should get a normal answer. It leaves out questions that should get a clarification, an abstention or a refusal, because there's no right chunk for those. It also leaves out two categories (version-and-date questions and prompt-injection questions) for reasons given in [ADR 0006](adr/0006-evals-with-deepeval-in-stages.md#retriever-golden-data).

## 4. Before you start

You need:

- the backend set up as in the [README](../README.md) (uv installed, a `.env` file at the repo root);
- the **dev collection ingested**, so the index has chunks. If you're not sure, run `uv run hr-assist ingest` from `backend/` (about a minute, and almost free);
- an `OPENAI_API_KEY` in `.env` that can use `gpt-5.6-luna`. The judge uses the same key as the app.

The eval reads the same settings as the app: `APP_ENV`, `CHUNKING_VERSION`, `EMBEDDING_MODEL`, `RETRIEVAL_K` and `RETRIEVAL_SCORE_THRESHOLD`. Together they decide which collection is searched and how. So **what you have in `.env` is what gets measured.**

You don't need to install anything extra. DeepEval is in its own `evals` dependency group, and the `--group evals` in the command below installs it the first time.

**Cost:** the judge isn't free. A full run costs about **$0.20**, and a 3-question smoke test about **$0.01**. Runs before 28 October 2026 used `gpt-6-sol`, which cost about $1.57 a run; their scores can't be compared with runs by the current judge.

## 5. How to run the retriever eval

Run every command from the **repo root** (the folder that holds `README.md`), not from `backend/`.

### Step 1: a smoke test (3 questions, about 15 seconds)

Do this first, to check everything is connected before you spend money on a full run:

```bash
uv run --project backend --group evals python evals/retrieval/run_eval.py --limit 3
```

At the end you should see something like:

```
                      Contextual Recall  Contextual Precision  questions
overall                           1.000                 0.983          3
factual_retrieval                 1.000                 0.983          3

Questions with no chunk retrieved: 0
Judge cost: $0.01
Wrote evals/results/retrieval/summary_20261028_074111.json
Wrote evals/results/retrieval/report_20261028_074111.md
```

A smoke test only covers 3 questions, so don't compare it with anything. Delete its three files from `evals/results/retrieval/` afterwards, so nobody mistakes it for a real run.

### Step 2: the full run (89 questions, a few minutes)

```bash
uv run --project backend --group evals python evals/retrieval/run_eval.py
```

You'll see a progress bar while the judge works, then the same table with a row for every category.

### Optional: use a different judge

```bash
uv run --project backend --group evals python evals/retrieval/run_eval.py --judge-model gpt-6-astra
```

You can also set `EVAL_JUDGE_MODEL=...` in `.env`. Scores from different judges **can't be compared**, so only do this on purpose, for example to test whether another judge agrees with human judgement.

### Step 3: keep the results

Each run writes three files to `evals/results/retrieval/`. Commit all three, so that later runs have something to compare against.

## 6. Reading the results

### The three files

| File | What's in it | Use it to |
| --- | --- | --- |
| `report_<time>.md` | The run's results for reading: the settings, the scores table, and every question with its expected answer, the judge's reasons and the start of each retrieved chunk. Lowest scores come first | **Start here** |
| `summary_<time>.json` | Mean scores overall and by category, each question's scores, which questions found no chunks, the judge cost, and every setting the run used | Compare runs |
| `test_run_<time>.json` | DeepEval's full record: the full text of every chunk retrieved, and the judge's verdicts | See a chunk's full text |

The report and the summary share a timestamp. The summary's `deepeval_run_file` field names the matching `test_run` file.

**Opening the report.** In VS Code, open the `report_*.md` file and press **Cmd+Shift+V** (Ctrl+Shift+V on Windows and Linux) for the preview. Once it's committed, GitHub shows it formatted too, including in a PR. Click a question to expand it.

**Why not DeepEval's own viewer?** `deepeval inspect` only shows *traces*, which these runs don't record, so it stops with "this test run has no traces". `deepeval view` uploads the run to Confident AI, DeepEval's hosted platform, and we keep results local (ADR 0006).

### How to look at a low score

1. Open the report. The questions are listed lowest score first, so the problems are at the top.
2. Click a question to see its expected answer, the judge's reason for each score, and the chunks that came back, in rank order.
3. If you need a chunk's full text, search the matching `test_run` file for the question ID (for example `NDS-EVAL-017`).
4. Usually one of these is true:
   - **the right chunk wasn't retrieved**: a search problem (chunking, embeddings, `RETRIEVAL_K`);
   - **it was retrieved but ranked low**: precision drops, recall doesn't;
   - **the judge got it wrong**: it happens. Note it, because the judge is checked against a hand-labelled sample (ADR 0006).

### "Questions with no chunk retrieved"

The last lines of a run print how many questions got no chunks at all, and their IDs. `0` is what you want.

When no chunk is relevant enough to pass `RETRIEVAL_SCORE_THRESHOLD`, the app replies with an abstention. The eval scores such a question **0** and lists it under `empty_retrievals`, so it still counts against the overall score. If this list is long, the threshold may be too strict.

### Don't over-read small differences

- Each question is about 1% of the overall score, so a change of **a point or two is noise**.
- Each category has only 11 to 14 questions. Use the category scores to **find weak spots**, not as exact measurements.
- The judge is an AI model, so the **same setup can score slightly differently** on two runs.

## 7. Comparing two setups

### What you can change

These settings change the retriever eval's scores. Set them in `.env`.

| Setting | Default | Production | What it does |
| --- | --- | --- | --- |
| `CHUNKING_VERSION` | `chunking_v2` | default | How documents are split into chunks: `chunking_v1` or `chunking_v2` |
| `CHUNK_MAX_TOKENS` | the version's own (500 for both) | default | The largest chunk size |
| `CHUNK_OVERLAP_TOKENS` | the version's own (v1: 60, v2: 100) | default | How much text neighbouring chunks of a split section share |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | set by deploy, same value | The model that turns text into vectors for search |
| `RETRIEVAL_K` | `3` | default | How many chunks come back for each question |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.65` | default | The lowest relevance a chunk needs. If none passes, the app abstains. `0` turns it off |
| `APP_ENV` | none (required) | `prod` | The first part of the collection name, so it picks which index is searched. Keep `development` for evals |

These belong to the eval only. The app never uses them:

| Setting | Default | What it does |
| --- | --- | --- |
| `EVAL_JUDGE_MODEL` in `.env`, or `--judge-model` on the command line | `gpt-5.6-luna` | The judge that scores the results. Scores from different judges can't be compared |
| `--limit N` on the command line | all 89 | Runs only the first N questions, as a smoke test |

Settings such as `CHAT_MODEL`, `REASONING_EFFORT` and `HISTORY_TURNS` change the answers but not the retrieval scores. They'll matter from the generation eval on. For every setting, see the [developer guide, section 4.2](developer-guide.md#42-every-setting).

Some things aren't settings and can only be changed in code: the prompt (`answering/prompt.py`), the search method (plain vector similarity), and the eval's metrics.

### `.env` or `settings.py`?

Change **`.env`**. It holds your own local settings, and both the app and the eval read it.

Don't change **`settings.py`** to experiment. It holds the defaults, and **production uses those defaults**. Production has no `.env`: the deploy workflow ([deploy.yml](../.github/workflows/deploy.yml)) sets only a few values itself (such as `APP_ENV`, `CHAT_MODEL` and `EMBEDDING_MODEL`). Everything else, including `CHUNKING_VERSION`, the chunk sizes, `RETRIEVAL_K` and `RETRIEVAL_SCORE_THRESHOLD`, comes from `settings.py`. A change there goes live on the next deploy.

Change `settings.py` only when an eval has shown that a new value is better and you want production to use it. Do it in a PR, with the two summaries as evidence.

> **To measure what production does, your `.env` must match production.** If your `.env` sets `RETRIEVAL_K=5` and production uses the default of `3`, the eval measures `5`. Before a run you'll use to make a decision, check the retrieval settings in your `.env` against the defaults in `settings.py`.

### Do I need to re-ingest?

| You change | Re-ingest? | Why |
| --- | --- | --- |
| `RETRIEVAL_K`, `RETRIEVAL_SCORE_THRESHOLD` | No | They only affect searching, not the chunks |
| `CHUNKING_VERSION` | Yes, once per version | Each version gets its own collection (for example `development-chunking_v1-text-embedding-3-small`), so v1 and v2 live side by side. Once both are ingested, switching between them is only a `.env` change |
| `EMBEDDING_MODEL` | Yes, once per model | Same reason: the collection name includes the model |
| `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS` | Yes, every time | **Careful:** the collection name doesn't include the sizes, so re-ingesting **overwrites** the current collection |

To re-ingest, run `uv run hr-assist ingest` from `backend/`.

### The steps

1. Run the eval with the current setup, and keep the summary.
2. Make **one** change in `.env`, so you know what caused any difference.
3. Re-ingest if the table above says so.
4. Run the eval again.
5. Compare the two summaries.
6. Set `.env` back to the setup the app should use. Your local app reads the same file.

**Runs from before [ADR 0007](adr/0007-search-only-current-documents.md) aren't comparable with later ones.** Until then, retrieval also searched superseded documents. The first `chunking_v1` run (`summary_20261028_075208.json`) is one of these, so run `chunking_v1` again before comparing it with `chunking_v2`.

Before comparing, check each summary's `hyperparameters`:

- **`judge_model` and `goldens_sha256` must be the same.** If either differs, the scores aren't comparable.
- **The chunk sizes are read from your `.env` at eval time**, not from the collection. If you changed the sizes without re-ingesting, the summary shows sizes the collection wasn't built with.

### Example: `chunking_v1` against `chunking_v2`

This is the comparison [ADR 0005](adr/0005-split-oversized-sections-at-unnumbered-headings.md) was waiting for. It was accepted on 2026-10-28, after `chunking_v2` scored at least as well as `chunking_v1`; repeat the comparison whenever chunking changes.

```bash
# 1. In .env set CHUNKING_VERSION=chunking_v1, then ingest it and run the eval:
cd backend && uv run hr-assist ingest && cd ..
uv run --project backend --group evals python evals/retrieval/run_eval.py

# 2. In .env set CHUNKING_VERSION=chunking_v2. It's the default, so it's probably
#    ingested already; if the eval says the collection doesn't exist, ingest it first.
uv run --project backend --group evals python evals/retrieval/run_eval.py
```

Then compare `means` in the two summaries: first `overall`, then each category. A difference of a point or two is noise (see [section 6](#dont-over-read-small-differences)). If one version is clearly worse in a category, look at that category's low-scoring questions in its `test_run` file to see why.

## 8. Building the golden files

### The source file and the golden files

All golden files come from one source file, `evals/eval_questions.json`. This file contains the 125 questions. Each question has a gold answer and its supporting passages.

Scripts make the golden files. Do not edit a golden file by hand.

| Golden file | Script | Eval |
| --- | --- | --- |
| `evals/retrieval/goldens_v1.jsonl` | `evals/retrieval/build_goldens.py` | Retriever eval (stage 2) |
| `evals/generation/goldens_v1.jsonl` | `evals/generation/build_goldens.py` | Generation eval (stage 3) |

Each script also writes a copy of the golden file in pretty-printed JSON, with the same name and the extension `.json`. For example, `evals/generation/goldens_v1.json`. Use this copy to read the goldens in an editor. The evals use only the `.jsonl` file. The two files always contain the same goldens, because the script writes them together.

Build the golden files again when:

- you change `evals/eval_questions.json`;
- you change the ingestion code or the chunking. This change affects only the generation goldens.

### The procedure

Do these steps from the repo root. Do step 1 before step 3, because the generation script reads its question list from the retriever goldens.

1. Build the retriever goldens:

   ```bash
   python evals/retrieval/build_goldens.py
   ```

2. Read the output. The script shows the number of goldens for each category, and the total. Today the total is 89.
3. Build the generation goldens:

   ```bash
   uv run --project backend python evals/generation/build_goldens.py
   ```

4. Read the output. The script shows:
   - how many questions have 1, 2, 3 or more gold chunks;
   - each supporting passage that has no chunk;
   - the file that it wrote.
5. Look at the changes with `git diff --stat evals/`. Commit the `.jsonl` file and its `.json` copy together. If you did not change the questions, the retriever goldens must stay the same.

The generation script uses the backend package. It reads the PDFs and decks in `data/` and makes the chunks again, in the same way as ingestion. It does not use Qdrant or OpenAI, so it costs nothing. It takes approximately 25 seconds.

### What the scripts check

The retriever script stops with an error when:

- two questions have the same ID;
- a question has no gold answer or no supporting passages;
- a question cites a Document ID that is not in `data/manifest.yaml`;
- the source file contains the section sign. Write "section 6.1".

The generation script stops with an error when a question has no gold chunk. When only one passage of a question has no chunk, the script does not stop. It shows that passage and records it in the golden. Today one passage has no chunk: the "Superseded notice" of `NDS-EVAL-082`. Ingestion removes this notice from the document.

### How the generation script finds the gold chunks

For each supporting passage of a question, the script:

1. takes the Document ID of the passage;
2. takes the section number at the start of the passage's section, for example "6.3" from "6.3, Table 6.3";
3. selects all chunks of that document in that section and in its subsections. For a deck, it selects the chunk of the slide, for example "Slide 6".

The script does not compare the quotes with the chunk text. The Document ID is necessary, because the same section number occurs in different documents.

The golden file keeps the full chunks, with their metadata. Thus each eval run gives the model the same evidence. The value of `RETRIEVAL_K` has no effect on the gold chunks.

### Golden files for a different chunking version

The generation script uses `chunking_v2` by default. To build the generation goldens for a different chunking version, give the version and a new file name:

```bash
uv run --project backend python evals/generation/build_goldens.py \
  --chunking chunking_v1 --output evals/generation/goldens_chunking_v1.jsonl
```

Do not write over `goldens_v1.jsonl` with a different chunking version. Each golden records its chunking version in `additional_metadata`.

### When you add or remove questions

Make a new version of the golden file, for example `goldens_v2.jsonl`. Do not write over v1. Scores from different question sets are not comparable, and a new file name makes this clear.

- For the retriever goldens, change `OUTPUT` in `evals/retrieval/build_goldens.py` and `GOLDENS` in `evals/retrieval/run_eval.py`.
- For the generation goldens, change `OUTPUT` and `RETRIEVAL_GOLDENS` in `evals/generation/build_goldens.py`.

## 9. How to run the generation eval

### What the generation eval checks

The generation eval checks the **answers only**. It does not search the index. For each golden, the runner:

1. gives the Answerer the gold chunks of the question, through a fake retriever;
2. sends the question to the real chat model, with the prompt and settings of the app;
3. asks the judge to score the reply.

Thus the model always has the correct evidence. A low score shows a problem in the model or the prompt, not in the search.

The eval uses the 89 questions of the generation goldens. These are the same questions as the retriever eval.

### The scores

| Score | What it measures |
| --- | --- |
| **Faithfulness** | Are all the claims in the reply supported by the gold chunks? 1.0 means that the reply adds nothing that the chunks do not say. |
| **Answer Relevancy** | Does the reply answer the question? 1.0 means that each statement in the reply is about the question. |

These scores do not compare the reply with the expected answer. A reply can be faithful and relevant, but incomplete. The report shows the expected answer, so that you can compare them yourself. Correctness and citations get scores in a later stage.

**Replies that are not an Answer.** Each question in the goldens must get an Answer. Sometimes the model replies with a Clarification, an Abstention or a Refusal. The judge does not score this reply. The reply gets 0 for the two scores, and the summary lists it under `non_answers`. Faithfulness would give such a reply a high score, because it makes no claims. The 0 prevents this.

**Errors.** When the chat model cannot be reached, or its reply cannot be read, the question gets 0 for the two scores. The summary lists it under `generation_errors`.

### Before you start

You need the items in [section 4](#4-before-you-start), but you do not need the index. The eval does not use Qdrant.

The eval uses the chat model settings in `.env`: `CHAT_MODEL`, `REASONING_EFFORT` and `MAX_OUTPUT_TOKENS`. The value of `RETRIEVAL_K` has no effect.

### The procedure

Do these steps from the repo root.

1. Do a smoke test with 3 questions:

   ```bash
   uv run --project backend --group evals python evals/generation/run_eval.py --limit 3
   ```

2. Make sure that the output shows a table of scores and the judge cost. The smoke test costs approximately $0.01 and takes approximately 2 minutes. The full run costs approximately $0.20.
3. Do the full run with the 89 questions:

   ```bash
   uv run --project backend --group evals python evals/generation/run_eval.py
   ```

4. Read the report. The output shows the path of the report.

To use a different judge, add `--judge-model <model>`. The judge must accept the parameter `temperature=0`. If the judge is not in the model list of DeepEval, DeepEval sends this value.

### The results

The runner writes three files in `evals/results/generation/`. The names of the files contain the date and time of the run.

| File | Contents |
| --- | --- |
| `test_run_*.json` | The DeepEval results: each verdict and reason of the judge. |
| `summary_*.json` | The settings of the run, the judge cost, the tokens of the chat model, the mean scores for all questions and for each category, and each reply with its scores. Use this file to compare runs. |
| `report_*.md` | The same results, for reading. Each question shows the question, the expected answer, the reply, the reasons of the judge and the gold chunks. The question with the lowest score is first. |

Compare two runs only when they used the same judge and the same goldens file. The summary records the two. The scores change a little between runs, also with the same settings, because the chat model and the judge do not always give the same output.

## 10. What comes next

Evals are built one stage at a time (ADR 0006):

| Stage | What it measures | Status |
| --- | --- | --- |
| 1. Retriever goldens | The 89 test questions for search | Done |
| 2. Retriever eval | Search quality | **Done ([section 5](#5-how-to-run-the-retriever-eval))** |
| 3. Generation eval | Answer quality when the model is given the right chunks | **Done ([section 9](#9-how-to-run-the-generation-eval))** |
| 4. Pipeline eval | Search and answering together, plus clarifications, abstentions and refusals | Not started |
| 5. Application eval | The live API over HTTP | Not started |
| 6. CI | Running the evals from GitHub Actions | Not started |

Until stage 6, evals are run by hand and never in CI. They cost money and their scores vary a little between runs, so they would make builds slow and unreliable.

## 11. Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| `Collection ... doesn't exist; ingest first` | No index for your current `.env` settings | Run `uv run hr-assist ingest` from `backend/` |
| `ValidationError` for `Settings` (for example `openai_api_key` missing) | `.env` is missing or incomplete | Copy `.env.example` to `.env` and fill it in |
| `No module named 'deepeval'` | The `evals` group wasn't included | Keep `--group evals` in the command |
| `can't open file '.../evals/retrieval/run_eval.py'` | You ran it from `backend/` | Run it from the repo root |
| `'temperature' does not support 0.0 with this model` | `EVAL_JUDGE_MODEL` names a model that DeepEval 4.3.2 does not know, and that model rejects `temperature=0` | Use `gpt-5.6-luna`, or give it with `--judge-model gpt-5.6-luna` |
| An OpenAI rate limit or authentication error | The key can't use `gpt-5.6-luna`, or is being rate-limited | Check the key's project in the OpenAI dashboard, then rerun |
| "Questions with no chunk retrieved" equals the number of questions | The collection is empty, or the threshold is too high | Re-ingest, and check `RETRIEVAL_SCORE_THRESHOLD` |
