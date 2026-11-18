# 07. Environment variables

All backend settings are read by one `Settings` class ([config/settings.py](../backend/src/hr_assist/config/settings.py)), built on `pydantic-settings`.

## How settings load

- From the **process environment**, then from **`.env` at the repo root**. The path is fixed, so the backend finds it whichever folder you start it from.
- **Empty values are ignored**, so `CHAT_MODEL=` in `.env` means "use the default".
- Unknown variables are ignored.
- Names are case-insensitive: `OPENAI_API_KEY` sets `openai_api_key`.
- Keys are `SecretStr`, so they don't appear in logs or reprs.
- A missing required value or a bad type stops start-up with a `ValidationError`.

```sh
cp .env.example .env   # then fill in the four required values
```

## Required

| Variable | Example | Notes |
| --- | --- | --- |
| `APP_ENV` | `development`, `prod` | Any name. It is the first part of the Qdrant collection name |
| `OPENAI_API_KEY` | `sk-...` | Used for the chat model and the embeddings |
| `QDRANT_URL` | `https://<cluster-id>.<region>.cloud.qdrant.io:6333` | |
| `QDRANT_API_KEY` | | |

## Models and generation

| Variable | Default | Notes |
| --- | --- | --- |
| `CHAT_MODEL` | `gpt-6-luna` | Must support structured output |
| `REASONING_EFFORT` | `low` | `none`, `low`, `medium`, `high`, `xhigh` or `max` |
| `MAX_OUTPUT_TOKENS` | `5000` | Caps each reply, **reasoning tokens included**. A higher effort needs a higher cap |
| `CHAT_TIMEOUT_SECONDS` | `60` | Per attempt |
| `CHAT_MAX_RETRIES` | `2` | Retries on a timeout, connection error, 408, 409, 429 or 5xx. Worst case: timeout × (retries + 1) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Part of the collection name. Changing it means re-ingesting |
| `EMBEDDING_TIMEOUT_SECONDS` | `20` | Ingestion sends up to 1000 chunks per request |

## Chunking (ingestion)

| Variable | Default | Notes |
| --- | --- | --- |
| `CHUNKING_VERSION` | `chunking_v2` | `chunking_v1` or `chunking_v2`. Part of the collection name. Also read by the API to pick the collection |
| `CHUNK_MAX_TOKENS` | the version's own (500) | **Not** part of the collection name, so re-ingesting with a new value overwrites the collection |
| `CHUNK_OVERLAP_TOKENS` | the version's own (v1: 60, v2: 100) | Must be smaller than the size limit |

## Retrieval and prompt

| Variable | Default | Notes |
| --- | --- | --- |
| `RETRIEVAL_K` | `3` | Chunks retrieved per question |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.65` | 0 to 1, on the `(cosine + 1) / 2` scale. With no chunk above it, the reply is an Abstention with no model call. `0` turns it off |
| `HISTORY_TURNS` | `5` | Recent messages included in the prompt |

## Tracing

| Variable | Default | Notes |
| --- | --- | --- |
| `LANGSMITH_TRACING` | `false` | `true` turns tracing on, if a key is also set |
| `LANGSMITH_API_KEY` | none | |
| `LANGSMITH_PROJECT` | none | LangSmith's own default project if unset |
| `LANGSMITH_ENDPOINT` | none | Only for EU accounts: `https://eu.api.smith.langchain.com` |

## API and usage limits

| Variable | Default | Notes |
| --- | --- | --- |
| `FRONTEND_ORIGIN` | `http://localhost:4200` | The one CORS origin allowed |
| `RATE_LIMIT_PER_MINUTE` | `20` | Chats per client IP in a rolling minute |
| `RATE_LIMIT_PER_DAY` | `100` | Chats per client IP per UTC day |
| `RATE_LIMIT_GLOBAL_PER_DAY` | `1000` | Chats answered per UTC day, all clients together |
| `TRUSTED_PROXY_HOPS` | `1` | `X-Forwarded-For` entries, counted from the right, added by proxies you trust. `0` ignores the header |

## Eval-only

| Variable | Default | Notes |
| --- | --- | --- |
| `EVAL_JUDGE_MODEL` | `gpt-5.6-luna` | The DeepEval judge. Read by the eval runners only, never by the app. `--judge-model` overrides it per run |

## The collection name

```python
f"{APP_ENV}-{CHUNKING_VERSION}-{EMBEDDING_MODEL}"
# development-chunking_v2-text-embedding-3-small
```

Ingestion writes this collection and the API reads it, so both must run with the same three values.

## Where each environment sets its values

| Environment | Source |
| --- | --- |
| Local backend and ingestion | `.env` at the repo root |
| Evals | The same `.env`. **Whatever is in `.env` is what gets measured** |
| CI tests | Nothing: tests build `Settings` themselves and use fakes |
| Production API (Cloud Run) | `--set-env-vars` and `--set-secrets` in [deploy.yml](../.github/workflows/deploy.yml). Everything else uses the defaults in `settings.py` |
| Production ingest | [ingest-prod.yml](../.github/workflows/ingest-prod.yml): `APP_ENV=prod`, `QDRANT_URL` from a repo variable, keys from Secret Manager |

Production sets:

```text
APP_ENV=prod
QDRANT_URL=<repo variable>
CHAT_MODEL=gpt-6-luna
EMBEDDING_MODEL=text-embedding-3-small
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=hr-assist-prod
FRONTEND_ORIGIN=https://hr-assist.naveenmanjappa.com
TRUSTED_PROXY_HOPS=<repo variable, or 1>
OPENAI_API_KEY, QDRANT_API_KEY, LANGSMITH_API_KEY  ← Secret Manager
```

Production has **no `.env`**. So a change to a default in `settings.py` goes live on the next deploy, while a change to your `.env` affects only your machine. Change a default only after an eval shows the new value is better ([12](12_EVALS_PIPELINE.md)).

## Frontend

The Angular app has one setting, `apiBaseUrl`, in `frontend/src/environments/`: `http://localhost:8000` for development, empty (same origin) for production ([06](06_FRONTEND.md)).
