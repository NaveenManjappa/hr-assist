---
status: accepted
---

# Search only current Source Documents, and park version-aware answers

Retrieval was pure vector similarity over every chunk in the collection, superseded ones included. The prompt was meant to sort out which Document Version applies, by working out each question's Applicable Date ([ADR 0002](0002-openai-models-and-two-step-rag.md)). In practice the superseded Leave Policy (`NDS-HR-LV-006`) crowds out the current one. For "what is the leave policy", its five "(historical)" chunks scored about 0.81 and filled all five places. The current Leave and Absence Standard (`NDS-HR-LAS-002`) came 7th and 8th, so the model never saw it and replied that its sources didn't cover the current leave policy.

We will **search only Source Documents whose Document Status is `current`**. `QdrantRetriever` adds a Qdrant payload filter on `metadata.status`, and ingestion creates the keyword index that Qdrant Cloud needs to filter on that field. Superseded documents stay in the Corpus Manifest and in the index, so bringing them back is a code change, not a re-ingest.

## What we give up

- **Version-aware answers.** Questions about a past date ("On 15 June 2026, what was the carryover rule?", "What was the allowance under the old leave policy?") can no longer find the superseded policy. The model answers from current documents. Their transitional arrangements cover some earlier dates; otherwise it abstains.
- **The As-Of Date control.** Answering as of a past date would search the same current documents, so the UI no longer offers it, and the "Version-aware" example questions are gone. The API still accepts `as_of_date`, and the frontend sends today's date.
- **The prompt's Applicable Date rules stay but rarely apply.** They are left as they are, because transitional rules inside current documents still name earlier dates, and they'll be needed again when version awareness returns.
- **Most `versioning_temporal` eval questions now expect answers the system can't give.** They were already left out of the retriever goldens ([ADR 0006](0006-evals-with-deepeval-in-stages.md)). Retriever eval runs from before this change searched superseded documents too, so they aren't comparable with runs after it.

## Considered options

- **Reserve places for superseded documents.** Search current documents for the top `k`, and separately take up to 2 superseded chunks. Current policy can't be crowded out, and history stays available. Not chosen for now: every question would carry old policy, and the prompt would still have to decide between the two.
- **An Applicable Date step before retrieval.** A small model call works out the question's Applicable Date, and retrieval keeps only documents in force on that date. The most accurate option, and the step ADR 0002 anticipated, but it adds a model call to every question and changes the two-step design.
- **Rerank or boost current documents.** Keeps everything searchable but still lets old chunks take places when they score much higher.

Version awareness should return through one of the first two, decided by the pipeline-level evals.

## Consequences

- Every collection needs the `metadata.status` index. Ingestion creates it. A collection built before this change must be re-ingested, or given the index by hand, **before** code with the filter runs against it; otherwise every search fails with "Index required but not found".
- The production collection, `prod-chunking_v2-text-embedding-3-small`, is one of these. Its index was added by hand in the Qdrant Cloud console on 2026-10-28 (`PUT collections/<name>/index` with `field_name` `metadata.status` and `field_schema` `keyword`), so deploying this change needs no extra step. Later prod ingests create the index themselves.
