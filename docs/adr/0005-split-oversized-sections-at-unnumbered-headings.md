---
status: accepted
---

# Split oversized sections at their unnumbered headings (`chunking_v2`)

`chunking_v1` ([ADR 0001](0001-document-loading-and-chunking.md)) packs an oversized section into parts of whole paragraphs, but it ignores the unnumbered headings inside the section. Worked examples, cards and appendices each start with one, so a part boundary can fall in the middle of an example. In the Leave and Absence Standard, section 3.4 (about 600 tokens) was cut after the first calculation of Worked example 3.4B. The second part held the bookable-leave answer (191.75 hours) but not the heading or scenario that says which case it is.

`chunking_v2` changes two things and keeps everything else from `chunking_v1`, including the 500-token size limit:

1. **An oversized section is split at its unnumbered headings.** The blocks are grouped so each group starts at a heading, and whole groups are packed into parts within the limit. Only a group that alone exceeds the limit is split as in `chunking_v1`, and its heading is repeated at the top of each later part. Section 3.4 now splits into the rule with Worked example 3.4A, and Worked example 3.4B on its own.
2. **Overlap 100 tokens, up from 60.** The overlap only applies inside a group that has to be split. Between groups there is none, because each group starts at a natural boundary and carries its own heading.

The metadata schema is unchanged. Chunk IDs keep the `{section_number}|{part}` key, so they differ from `chunking_v1` only where the parts differ.

The size limit and overlap are the strategy's defaults. `CHUNK_MAX_TOKENS` and `CHUNK_OVERLAP_TOKENS` override them at ingestion, but they are not part of the collection name, so ingesting new sizes under the same version replaces that collection.

## Effect on the corpus

| | `chunking_v1` (500/60) | `chunking_v2` (500/100) |
|---|---|---|
| Chunks | 405 | 408 |
| Sections split into parts | 10 | 10 (the same ones) |
| Largest chunk body | about 900 tokens (Table R) | about 900 tokens (Table R, unchanged: tables are never split) |

The same sections are split, but at different points. Three of them (Handbook sections 6.3 and 8, and the Appendices) get one more part each, because packing whole groups leaves some parts short of the limit.

## Rollout

`CHUNKING_VERSION` selects the strategy at ingestion (`STRATEGIES` in `ingestion/chunking.py`) and names the collection, so `chunking_v2` builds a new collection beside the `chunking_v1` one. `chunking_v2` is the default. Production reads its version from that default, so run **Ingest (prod)** from the branch before merging, otherwise the deployed API looks for a collection that doesn't exist yet. Accepted on 2026-10-28, once the retriever eval ([ADR 0006](0006-evals-with-deepeval-in-stages.md)) showed `chunking_v2` scores at least as well as `chunking_v1`. Over all 89 questions, with `retrieval_k` 5, current documents only and `gpt-6-sol` as judge, two `chunking_v2` runs scored recall 0.856 and 0.836 and precision 0.904 and 0.907; `chunking_v1` scored 0.844 and 0.898. The difference is within the judge's run-to-run variation (2 points of recall between the two identical `chunking_v2` runs), so `chunking_v2` is as good, not measurably better. The runs are in `evals/results/retrieval/`.

The versions were first named `structure_v1` and `structure_v2`. They were renamed before `chunking_v2` reached production, so a collection named `prod-structure_v1-…` holds `chunking_v1` chunks and can be deleted once `prod-chunking_v2-…` is serving.

## Considered options

- **Raise the limit to 800**: keeps section 3.4 whole and splits only 4 sections, but makes every retrieved chunk larger, so each question sends more tokens to the model.
- **Only raise the limit, without splitting at headings**: the sections still over the limit (Leave and Absence Standard section 5, Expenses sections 14 and 15, Handbook Appendices) would still be cut mid-example.
- **Put the sub-heading in `section_path` or a new metadata field**: would help citations, but changes the metadata schema the API and UI read. Repeating the heading in the body is enough for retrieval.
