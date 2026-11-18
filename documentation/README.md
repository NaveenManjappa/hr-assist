# HR Assist documentation

This folder documents HR Assist one topic per file. Each file stands on its own, so you can open only the one you need. Read them in order to learn the whole system, from what it is to how it is measured and shipped.

HR Assist is a chat assistant that answers Northstar Digital Services employees' HR policy questions. It answers only from a fixed set of policy PDFs and summary decks, and every answer cites the document, version, section and page (or slide) it relies on.

## Reading order

| # | File | Read it to learn |
| --- | --- | --- |
| 01 | [System overview](01_SYSTEM_OVERVIEW.md) | What HR Assist does, its parts, the tech stack, and the path of one question |
| 02 | [Corpus and manifest](02_CORPUS_AND_MANIFEST.md) | Which documents it answers from, and how the Corpus Manifest describes them |
| 03 | [Ingestion engine](03_INGESTION_ENGINE.md) | How PDFs and decks become searchable chunks in Qdrant |
| 04 | [Answering engine](04_ANSWERING_ENGINE.md) | How a question becomes a typed, cited reply: retrieval, prompt, generation, citations |
| 05 | [API reference](05_API_REFERENCE.md) | The two endpoints, request and response shapes, errors and headers |
| 06 | [Frontend](06_FRONTEND.md) | The Angular chat UI: components, state, citations, connection status |
| 07 | [Environment variables](07_ENVIRONMENT_VARIABLES.md) | Every setting, its default, and where each environment sets it |
| 08 | [Guardrails and usage limits](08_GUARDRAILS_AND_USAGE_LIMITS.md) | Grounding, Refusals, prompt-injection defence, validation, rate limits, spending caps |
| 09 | [Tracing and observability](09_TRACING_AND_OBSERVABILITY.md) | Request IDs, log lines, LangSmith tracing, and how to debug a failed request |
| 10 | [Testing](10_TESTING.md) | The pytest and Vitest suites, the fakes, and what CI runs |
| 11 | [Evals](11_EVALS.md) | How answer quality is measured: the four eval levels, the metrics, the latest scores |
| 12 | [Evals pipeline](12_EVALS_PIPELINE.md) | How to build goldens, run an eval, read its report, and compare setups |
| 13 | [Deployment and CI/CD](13_DEPLOYMENT_AND_CI.md) | Cloud Run, Firebase Hosting, the GitHub Actions workflows, secrets and costs |
| 14 | [Known gotchas](14_KNOWN_GOTCHAS.md) | Non-obvious behaviour that has caught people out, and how to avoid it |
| 15 | [Limitations and roadmap](15_LIMITATIONS_AND_ROADMAP.md) | What the system can't do yet, and the planned next steps |

## Quick start

```sh
cp .env.example .env              # fill in APP_ENV, OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY
cd backend && uv sync
uv run hr-assist ingest           # build the Qdrant collection (about a minute)
cd .. && npm run dev              # backend on :8000 and frontend on :4200 together
```

Then open <http://localhost:4200> and ask "How much annual leave do I get after 4 years?". [01 System overview](01_SYSTEM_OVERVIEW.md) explains what happens next.

## How this folder relates to the rest of the repo

This folder is the map. Some topics have a longer, step-by-step document elsewhere, and the files here link to them:

| Where | What it holds |
| --- | --- |
| [README.md](../README.md) | Project summary and the local setup steps |
| [GLOSSARY.md](../GLOSSARY.md) | The domain terms (Corpus, Effective Period, Response Type and so on). This folder uses them with the same meaning |
| [docs/developer-guide.md](../docs/developer-guide.md) | One long guide to the whole back end |
| [docs/deployment.md](../docs/deployment.md) | Why and how the system is deployed, with the decision log |
| [docs/deployment-setup.md](../docs/deployment-setup.md), [docs/go-live.md](../docs/go-live.md) | One-time cloud setup and custom-domain runbooks |
| [docs/evals.md](../docs/evals.md) | The evals guide |
| [docs/adr/](../docs/adr/) | Architecture decision records 0001 to 0007 |

When code and a document disagree, the code is right. The facts in this folder were checked against the code on 18 November 2026, on the `feature/evals-guardrails` branch.

## Domain words in one minute

| Term | Meaning |
| --- | --- |
| **Corpus** | The Source Documents HR Assist answers from. Only files listed in the Corpus Manifest belong to it |
| **Policy Document** | An authoritative PDF that sets rules |
| **Summary Deck** | A non-authoritative PPTX that summarises policy. A Policy Document always prevails over it |
| **Document Status** | `current` or `superseded` |
| **Effective Period** | The dates a Document Version was in force |
| **Employee** | The anonymous person asking a question |
| **As-Of Date / Applicable Date** | The day the question is asked / the day the question is about |
| **Response Type** | Answer, Clarification, Abstention or Refusal |
| **Citation** | Document title, ID, version, section, and page or slide behind an Answer |

The full definitions are in [GLOSSARY.md](../GLOSSARY.md).
