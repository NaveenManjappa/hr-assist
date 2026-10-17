---
status: accepted
---

# Load PDFs as Markdown, describe documents in a Corpus Manifest, and chunk by section

HR policy answers depend on three things that plain text extraction loses: which section a rule belongs to, the rows of tables (11 of the eval questions are table lookups), and which version of a document was in force. We load PDFs through `PyMuPDF4LLMLoader` to get Markdown, which keeps headings and pipe tables. We take document facts from a hand-written Corpus Manifest, not from the files. We chunk one section at a time, and split a section further only when it exceeds the size limit.

## Pipeline

```
manifest.yaml ─┐
               ▼
PDF ──► PyMuPDF4LLMLoader(mode="page") ──► normaliser ──► MarkdownHeaderTextSplitter ──► oversize split ──► embed ──► Qdrant
PPTX ─► python-pptx (one unit per slide, notes included) ─────────────────────────────────┘
```

1. **Load** each PDF page as Markdown, keeping its page number.
2. **Normalise**: strip the running header (`Leave and Absence Standard | NDS-HR-LAS-002 | v1.2`, `**Northstar Digital Services Ltd.**`) and the table-of-contents pages, then join the pages with page markers so a section can cross a page break.
3. **Split by section** with `MarkdownHeaderTextSplitter` on `#`, `##` and `###`. Each chunk gets its section path and its `page_start` and `page_end`.
4. **Split oversized sections** with `RecursiveCharacterTextSplitter` (~500 tokens, ~60 overlap), keeping tables and worked examples whole where possible.
5. **Decks**: one chunk per slide, containing the title, body text, tables rendered as Markdown, and speaker notes. The notes hold policy content that isn't on the slide.

The loader and the chunker sit behind our own `Parser` and `ChunkingStrategy` interfaces. The chunking config is versioned (`structure_v1`), and that version is part of the Qdrant collection name.

## Example

Page 5 of NDS-HR-LAS-002 with `pypdf` (rejected):

```
Less than 3 years
27
8
35
```

The same page with `pymupdf4llm`:

```md
## **3.1 Entitlement**
|**Continuous service completed**|**Annual leave**|**Bank holidays**|**Total days**|**Total hours**|
|Less than 3 years|27|8|35|262.5|
```

This becomes one chunk. Its text, as embedded:

```
Leave and Absence Standard (NDS-HR-LAS-002 v1.2, current, effective 2026-10-01)
3 Annual leave > 3.1 Entitlement

Table 3.1 — Annual leave entitlement (full-time, 37.5 hours over 5 days)
|Continuous service completed|Annual leave|Bank holidays|Total days|Total hours|
|Less than 3 years|27|8|35|262.5|
...
```

Its metadata:

```json
{"document_id": "NDS-HR-LAS-002", "document_version": "v1.2", "title": "Leave and Absence Standard",
 "document_kind": "policy_document", "status": "current", "effective_from": "2026-10-01", "effective_to": null,
 "section_number": "3.1", "section_title": "Entitlement", "section_path": ["3 Annual leave", "3.1 Entitlement"],
 "page_start": 5, "page_end": 5, "chunking_version": "structure_v1"}
```

## Corpus Manifest

`data/manifest.yaml` is the single list of what gets ingested and what each file *is*:

```yaml
- path: data/policies/02_Leave_and_Absence_Standard_v1.2.pdf
  document_id: NDS-HR-LAS-002
  document_version: v1.2
  title: Leave and Absence Standard
  kind: policy_document          # policy_document | summary_deck | test_fixture
  status: current                # current | superseded
  effective_from: 2026-10-01
  effective_to: null

- path: data/policies/archived/06_ARCHIVED_Superseded_Leave_Policy_v1.0.pdf
  document_id: NDS-HR-LV-006
  document_version: v1.0
  title: Leave Policy
  kind: policy_document
  status: superseded
  effective_from: 2025-01-01
  effective_to: 2026-09-30
  superseded_by: NDS-HR-LAS-002
```

**Why a manifest rather than parsing the facts out of the files:**
- The kind of a document (Policy Document, Summary Deck or Test Fixture) and its Effective Period drive precedence and date reasoning. A wrong value here produces confidently wrong answers, so these facts should be explicit and reviewable in a diff.
- The PDFs print these facts in a running header, but the decks don't do it consistently, and the archived policy has no effective end date in its header.
- Ingesting only the files listed in the manifest means the `evals/` files can't be ingested by accident.
- Ingestion checks the manifest against the PDF running header and fails if the Document ID or Version disagree. This catches a manifest entry that has drifted from its file.

**Adding or updating a document:** put the file under `data/`, add or edit its manifest entry (when a new version replaces an old one, mark the old entry `superseded` and give it an `effective_to`), then run `uv run hr-assist ingest`. Ingestion rebuilds the whole collection, which takes about a minute for this corpus, so we don't need incremental update logic yet.

## Considered options

- **`pypdf` / `PyPDFLoader`**: flattens tables and loses headings. It also lives in `langchain-community`, which is no longer maintained.
- **`docling`**: better at complex tables, but brings a heavy ML stack and slow startup. It is the fallback if table questions score poorly.
- **Fixed-size recursive chunking only**: simpler, but splits rules away from their conditions and tables away from their captions. We will compare it against this approach once evals exist.
- **Metadata from filenames**: brittle, and can't express Effective Periods.

## Consequences

- `pymupdf4llm` is AGPL-3.0. That's acceptable for a public portfolio repo, but would need revisiting for closed-source use.
- It pulls in `onnxruntime` and a layout model (~60 MB). Ingestion is an offline CLI step, so the deployed API doesn't carry this weight.
- Changing the chunking means a new `chunking_version` and a new collection, and the old collection stays available for comparison.
