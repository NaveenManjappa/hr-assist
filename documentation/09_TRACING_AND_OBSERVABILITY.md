# 09. Tracing and observability

Three tools tell you what HR Assist did with a request:

| Tool | Answers | Where |
| --- | --- | --- |
| **Request IDs** | Which log lines belong to this request? | `X-Request-ID` header and every log line |
| **Application logs** | What happened, how long it took, which prompt and chunks were used, what it cost in tokens | stdout locally; Cloud Run → Logs in production |
| **LangSmith traces** | What exactly went into the model, and what came back? | smith.langchain.com, project `hr-assist-prod` in production |

## Request IDs

`RequestIdMiddleware` ([api/request_id.py](../backend/src/hr_assist/api/request_id.py)) gives every HTTP request an ID:

1. If the request has an `X-Request-ID` matching `^[A-Za-z0-9._-]{1,64}$`, it is used. A caller can then follow its own ID through the logs.
2. Otherwise a random 32-character hex ID is generated. Invalid incoming values are replaced, so log lines can't be forged through the header.
3. The ID is stored in a `ContextVar`, so every log line written while handling the request includes it, even in async code.
4. It is returned in the `X-Request-ID` response header, on every response including `422`, `429`, `503` and `500`, and inside every error body as `error.request_id`.

## Log format

`configure_logging()` sets up the `hr_assist` logger once, at `INFO`, writing to stderr:

```text
%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s
```

Lines outside a request show `[-]`.

### The log lines you'll see

| Logger | Level | When | Example |
| --- | --- | --- | --- |
| `hr_assist.request` | INFO | Every request, when it finishes | `POST /api/chat -> 200 in 2143.7ms` |
| `hr_assist.chat` | INFO | Every chat that reaches the Answerer | `chat response_type=answer prompt=v7 latency_ms=2140 chunks=[...] token_usage={...}` |
| `hr_assist.rate_limit` | INFO | Every chat: how the client IP was chosen | `X-Forwarded-For='198.51.100.4, 66.249.93.7' peer=169.254.1.1 hops=2 client=198.51.100.4` |
| `hr_assist.rate_limit` | WARNING | A chat is rate-limited | `Rate limited: per_ip_minute limit hit by 198.51.100.4, retry after 37s` |
| `hr_assist.errors` | ERROR | Qdrant or OpenAI failed | `Upstream failure: Searching the policy index failed.` plus the traceback with the real cause |
| `hr_assist.errors` | ERROR | Any unhandled exception | `Unhandled error on POST /api/chat` plus the traceback |

The chat line is the most useful. It records:

- `response_type`: what kind of reply was given
- `prompt`: the `PROMPT_VERSION`, or `none` when the no-evidence Abstention skipped the model
- `latency_ms`: retrieval plus generation
- `chunks`: the IDs of the retrieved chunks (stable across rebuilds, see [03](03_INGESTION_ENGINE.md))
- `token_usage`: input, output and total tokens

Logs are plain text, not JSON, so Cloud Logging can't filter on fields like `response_type` directly. Search the text instead.

## LangSmith tracing

[integrations/langsmith.py](../backend/src/hr_assist/integrations/langsmith.py) turns tracing on only when **both** `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are set. LangChain reads LangSmith settings from the process environment, so `configure_tracing` exports them there at start-up.

Each chat becomes one trace:

```text
chat                 @traceable on Answerer.answer: the request and the ChatResponse
├── retrieve         the Qdrant retriever: the query and the returned documents with scores
└── generate         the OpenAI call: the full prompt, the structured reply, token usage
```

The run names `retrieve` and `generate` are set in the adapters, so traces read the same whatever the underlying classes are called.

- **Locally:** optional. Set the variables in `.env` to see your own requests.
- **In production:** on, in the project `hr-assist-prod`. Real questions become material for eval sets. The UI tells visitors on first load that questions are logged.
- **EU accounts** also need `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com`.
- **The evals** use the same `Settings`, so they're traced too if `.env` turns tracing on.

## Health

`GET /api/health` reports `api` and `qdrant` status ([05](05_API_REFERENCE.md)). Three things use it:

| Caller | How often | On failure |
| --- | --- | --- |
| The UI's connection indicator | Every 30 seconds | Shows "Qdrant unreachable" or "API unreachable" |
| [scripts/smoke-test.sh](../scripts/smoke-test.sh), after each deploy | Every 10 seconds, for up to 300 seconds | The Deploy workflow fails |
| [Qdrant keep-alive](../.github/workflows/qdrant-keep-alive.yml) | Mondays and Thursdays at 06:17 UTC | The workflow fails if Qdrant isn't `up` |

## Debugging a failed request

1. Get the request ID: from the error body's `request_id`, the `X-Request-ID` response header, or the browser's network tab.
2. Find its lines:
   - Locally: search the backend's terminal output.
   - Production: Cloud Run → `hr-assist-api` → Logs, and search for the ID.
3. Read the `Upstream failure` or `Unhandled error` traceback for the real cause.
4. For a wrong answer rather than an error, open the LangSmith trace for that time and read the `retrieve` and `generate` runs: were the right chunks found, and what did the model see?

| You see | Likely cause |
| --- | --- |
| `503`, "Searching the policy index failed.", cause "Not found: Collection ..." | The collection for this `APP_ENV`, chunking version and embedding model hasn't been built. Run ingestion |
| `503`, cause "Index required but not found" for `metadata.status` | The collection predates [ADR 0007](../docs/adr/0007-search-only-current-documents.md). Re-ingest, or add the keyword index by hand |
| `503`, "The language model could not be reached.", cause an OpenAI 429 `project_spend_limit_exceeded` | The $10 monthly hard limit was reached |
| `503`, "...returned a reply that could not be read." | Structured output failed to parse, often because the reply ran out of tokens. Check `MAX_OUTPUT_TOKENS` against `REASONING_EFFORT` |
| `504` from Firebase | The request took over Firebase Hosting's 60-second limit |
| Many `response_type=abstention prompt=none` lines | Retrieval returns nothing. The collection may be empty, or `RETRIEVAL_SCORE_THRESHOLD` is too high |
