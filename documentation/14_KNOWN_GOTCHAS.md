# 14. Known gotchas

Non-obvious behaviour that has caught people out, why it happens, and what to do. Each entry follows the same pattern: **Issue**, **Reason**, **Solution**.

---

## 1. Changing chunk sizes overwrites the collection

**Issue.** You set `CHUNK_MAX_TOKENS=800` to try bigger chunks, re-ingest, and your 500-token collection is gone.

**Reason.** The collection name is `<APP_ENV>-<CHUNKING_VERSION>-<EMBEDDING_MODEL>`. The sizes aren't part of it, so a re-ingest with new sizes writes to the same name, and ingestion always drops and recreates.

**Solution.** To keep both, also change `APP_ENV` (for example `development-big`) for the experiment. Remember that eval summaries read the sizes from `.env` at run time, not from the collection.

---

## 2. Health says `ok` while every chat fails

**Issue.** `/api/health` returns `{"status":"ok"}`, but every chat returns `503` "Searching the policy index failed."

**Reason.** The health check only lists collections to prove the Qdrant **cluster** is reachable. It doesn't check that **this** collection exists. A new `APP_ENV`, chunking version or embedding model points at a collection nobody has built yet.

**Solution.** Run ingestion with the same settings (`uv run hr-assist ingest` locally, **Ingest (prod)** in production). The traceback in the logs says "Not found: Collection ...".

---

## 3. "Index required but not found" on `metadata.status`

**Issue.** Searches fail with an error about a missing index.

**Reason.** Retrieval filters on `metadata.status` ([ADR 0007](../docs/adr/0007-search-only-current-documents.md)), and Qdrant Cloud refuses to filter on an unindexed field. Collections built before that change have no such index.

**Solution.** Re-ingest; `rebuild_index` creates the keyword index. Or add it by hand: `PUT collections/<name>/index` with `field_name: metadata.status`, `field_schema: keyword`.

---

## 4. Ingestion and its tests need the internet once

**Issue.** On a new machine or in a sandbox, `hr-assist ingest` and the ingestion tests fail with a proxy or connection error, while the other tests pass.

**Reason.** The chunker counts tokens with `tiktoken.get_encoding("o200k_base")`. On first use, `tiktoken` downloads the encoding file and caches it.

**Solution.** Run once with internet access, or set `TIKTOKEN_CACHE_DIR` to a folder that already holds the file.

---

## 5. A PDF produces 0 chunks

**Issue.** Ingestion prints `NDS-XXX v1.0: 0 chunks` for a new document.

**Reason.** PDF chunking starts a section only at a Markdown heading that begins with a number (`## 3.1 Title`), and drops everything before the first one. A document without numbered headings has no sections.

**Solution.** Check how PyMuPDF4LLM renders the document's headings. If the document truly has no numbered sections, it needs a new chunking strategy ([03](03_INGESTION_ENGINE.md)).

---

## 6. Ingestion fails with "its running header says ..."

**Issue.** `ManifestError: Manifest describes X.pdf as NDS-HR-LAS-002 v1.3, but its running header says NDS-HR-LAS-002 v1.2`.

**Reason.** Ingestion checks every page header (or a deck's title slide) against the manifest, so an entry can't silently drift from its file.

**Solution.** This is working as intended. Fix whichever is wrong: the manifest entry or the file.

---

## 7. Your `.env` is not production

**Issue.** An eval looks great, you merge, and production behaves differently. Or you change a default in `settings.py` "just to test" and it goes live.

**Reason.** Production has no `.env`. It uses the defaults in `config/settings.py` plus the few values in [deploy.yml](../.github/workflows/deploy.yml). Evals and your local app use your `.env`. The latest recorded eval runs, for instance, used `RETRIEVAL_K=5` and `REASONING_EFFORT=medium`, while production uses 3 and `low`.

**Solution.** To measure production, make your `.env` match it. Change `settings.py` only in a PR backed by eval summaries.

---

## 8. Higher reasoning effort can produce `503`s

**Issue.** After raising `REASONING_EFFORT`, some chats return `503` "The language model returned a reply that could not be read."

**Reason.** Reasoning tokens count against `MAX_OUTPUT_TOKENS`. If reasoning uses up the budget, the structured reply is cut short and can't be parsed.

**Solution.** Raise `MAX_OUTPUT_TOKENS` together with the effort, and keep the spending cap in mind.

---

## 9. Literal braces in the prompt break it

**Issue.** After editing `prompts/answer.md`, every chat fails with a `KeyError` or `IndexError`.

**Reason.** The prompt is filled with Python's `str.format`, which treats `{...}` as a placeholder.

**Solution.** Keep `{as_of_date}` and `{sources}`; write any other brace as `{{` or `}}`. Bump `PROMPT_VERSION` while you're there.

---

## 10. `TRUSTED_PROXY_HOPS` depends on the path

**Issue.** Through Firebase, all visitors seem to share one rate-limit bucket; or a bot dodges the per-IP limits.

**Reason.** Through Firebase, `X-Forwarded-For` is `<visitor>, <Google proxy>`, so the visitor is 2nd from the right. On the direct `run.app` URL, the visitor is 1st. With `1` hop, every Firebase visitor is counted as Google's proxy. With `2`, a direct caller can add a forged entry.

**Solution.** Production uses `2`, set as a repo variable, because the Firebase path is the one real visitors use. The direct path keeps the global cap and the OpenAI hard limit. Every chat logs the header and the chosen client, so you can re-measure.

---

## 11. Re-ingesting production causes a minute of bad answers

**Issue.** During **Ingest (prod)**, chats fail or abstain.

**Reason.** `rebuild_index` uses `force_recreate=True`: the collection is dropped, then filled.

**Solution.** Run it when traffic is low. The lasting fix is to build a new collection and switch a Qdrant alias ([15](15_LIMITATIONS_AND_ROADMAP.md)).

---

## 12. Rate-limit counters reset on restart

**Issue.** A visitor who hit the daily limit can ask again after a deploy.

**Reason.** The counters live in the single instance's memory. A new revision, or a scale to zero and back, starts from zero.

**Solution.** Acceptable for a demo. A shared store (Redis, Firestore) would fix it and allow more than one instance.

---

## 13. A DOCS folder is the same as docs on macOS

**Issue.** Creating `DOCS/` next to `docs/` writes into `docs/`.

**Reason.** macOS file systems are case-insensitive by default, while Git and Linux CI are case-sensitive.

**Solution.** Never create paths that differ only by case. This folder is called `documentation/` for that reason.

---

## 14. The eval runners must run from the repo root

**Issue.** `can't open file '.../run_eval.py'` or `No module named 'deepeval'`.

**Reason.** The commands use paths relative to the repo root, and DeepEval is in the optional `evals` dependency group.

**Solution.** Run from the root, and keep `--project backend --group evals` in the command ([12](12_EVALS_PIPELINE.md)).

---

## 15. Scheduled workflows go quiet

**Issue.** The Qdrant cluster was suspended even though the keep-alive exists.

**Reason.** GitHub runs schedules only from the default branch, and disables them after 60 days with no repository activity. The keep-alive is also a no-op while `API_URL` is empty.

**Solution.** Re-enable the workflow from the Actions tab, and check `API_URL` is set.
