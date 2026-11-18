# 05. API reference

The backend is a FastAPI app built by `create_app()` in [api/app.py](../backend/src/hr_assist/api/app.py). It has two endpoints, both under `/api/` so Firebase Hosting can forward them.

| Method and path | Purpose | Rate-limited |
| --- | --- | --- |
| `POST /api/chat` | Answer a question | Yes |
| `GET /api/health` | Report whether the API and Qdrant are up | No |

FastAPI also serves its generated docs at `/docs` (Swagger UI), `/redoc` and `/openapi.json`.

Run it locally from `backend/`:

```sh
uv run uvicorn hr_assist.api.app:create_app --factory --reload   # http://localhost:8000
```

## `POST /api/chat`

### Request

```json
{
  "messages": [
    { "role": "user", "content": "How much annual leave do I get?" },
    { "role": "assistant", "content": "Do you work full-time or part-time?" },
    { "role": "user", "content": "Full-time, 4 years' service." }
  ],
  "as_of_date": "2026-11-18"
}
```

| Field | Type | Rules |
| --- | --- | --- |
| `messages` | list | 1 to 20 items. **The last one must have `role: "user"`** |
| `messages[].role` | `"user"` or `"assistant"` | |
| `messages[].content` | string | Whitespace is trimmed, then 1 to 4000 characters |
| `as_of_date` | `YYYY-MM-DD` or omitted | The As-Of Date. Omitted means the server's today (UTC on Cloud Run) |

The API is stateless: the client sends the history it wants considered. Only the last 5 messages reach the model, and only the last 2 Employee messages are used for search ([04](04_ANSWERING_ENGINE.md)).

### Response `200`

```json
{
  "response_type": "answer",
  "message": "Full-time employees with 4 years' service get 27 days plus bank holidays [1].",
  "citations": [
    {
      "document_id": "NDS-HR-LAS-002",
      "document_version": "v1.2",
      "title": "Leave and Absence Standard",
      "section": "3.1 Entitlement",
      "page_start": 4,
      "page_end": 4,
      "slide": null,
      "snippet": "**Table 3.1 ...**\n\n|...|",
      "status": "current"
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `response_type` | `answer`, `clarification`, `abstention` or `refusal` |
| `message` | Plain text. In an Answer, markers `[1]`, `[2]`... match the order of `citations` |
| `citations` | Empty unless the reply cites sources. A PDF Citation has `page_start` and `page_end` and `slide: null`; a deck Citation has `slide` and null pages |
| `citations[].section` | `"<number> <title>"` for a PDF section, or the slide title |
| `citations[].snippet` | The whole chunk body, as Markdown (headings, bold, pipe tables, lists) |

### Example

```sh
curl -s localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"How much annual leave do I get after 4 years?"}]}' | jq
```

## `GET /api/health`

```json
{ "status": "ok", "api": "up", "qdrant": "up" }
```

| `status` | `qdrant` | Meaning |
| --- | --- | --- |
| `ok` | `up` | Qdrant answered a list-collections call within 5 seconds |
| `degraded` | `down` | The API is up but can't reach Qdrant |

It always returns `200` when the API is running. It checks that the Qdrant **cluster** is reachable, **not that the collection exists**, so it can say `ok` while every chat fails because the collection hasn't been built ([14](14_KNOWN_GOTCHAS.md)).

Callers: the UI's connection indicator (every 30 seconds), the deploy smoke test, and the twice-weekly Qdrant keep-alive.

## Errors

Every error the app produces has one shape:

```json
{
  "error": {
    "code": "rate_limited",
    "message": "You're asking questions too quickly. Please wait a minute and try again.",
    "details": [],
    "request_id": "4f0c2a9e7d3b4a51b2c8e1f0a6d9c3b7"
  }
}
```

| Status | `code` | When | `message` |
| --- | --- | --- | --- |
| `422` | `validation_error` | The body breaks a rule above | "The request is invalid." `details` lists each problem as `{loc, msg, type}` |
| `429` | `rate_limited` | A per-IP or global limit is reached. Has a `Retry-After` header in seconds | A message naming the limit ([08](08_GUARDRAILS_AND_USAGE_LIMITS.md)) |
| `503` | `upstream_unavailable` | Qdrant or OpenAI failed, timed out, or returned an unreadable reply | "Searching the policy index failed." or "The language model could not be reached." or "...returned a reply that could not be read." |
| `500` | `internal_error` | Any other unhandled exception | "Something went wrong. Please try again." |

The real cause of a `503` or `500` is **logged with its traceback, never returned**. Find it with the `request_id` ([09](09_TRACING_AND_OBSERVABILITY.md)).

FastAPI's own `404` and `405` responses still use its default `{"detail": "..."}` shape.

## Headers

| Header | Direction | Notes |
| --- | --- | --- |
| `X-Request-ID` | Request (optional) and response (always) | Pass your own (1 to 64 of `A-Z a-z 0-9 . _ -`) to correlate; otherwise a random hex ID is generated. Exposed to browsers through CORS |
| `X-Forwarded-For` | Request | Used to find the client IP for rate limits, trusting `TRUSTED_PROXY_HOPS` entries from the right |
| `Retry-After` | Response on `429` | Seconds until the limit's window resets |
| CORS | Response | Allows only `FRONTEND_ORIGIN`, methods `GET` and `POST`, headers `Content-Type` and `X-Request-ID` |

## Middleware order

Starlette runs the last-added middleware outermost. In `create_app` the order from the outside in is:

```text
CORSMiddleware            adds CORS headers, answers preflights
  RequestIdMiddleware     sets X-Request-ID, logs "METHOD path -> status in N ms"
    InternalErrorMiddleware   turns an unhandled exception into the 500 envelope
      FastAPI routes + exception handlers (422, 429, 503)
```

`InternalErrorMiddleware` sits **inside** the other two. Starlette's default 500 handler runs outside all middleware, so its responses would lose the request ID and CORS headers, and the browser couldn't even read them. Both custom middlewares are pure ASGI, not `BaseHTTPMiddleware`.

## Dependency injection

```python
create_app(
    settings: Settings | None = None,
    vector_store: VectorStore | None = None,   # health check
    retriever: Retriever | None = None,
    chat_model: ChatModel | None = None,
    clock: Clock = utc_now,                    # rate limiter
)
```

Anything left as `None` gets the real adapter. Tests pass fakes. The real Qdrant clients are closed on shutdown through the app's lifespan.

## Adding an endpoint

1. Add a router module in `api/`, with Pydantic request and response models.
2. Put its path under `/api/`, so Firebase forwards it.
3. Include the router in `create_app`.
4. Raise `UpstreamError` for dependency failures, so the shared envelope applies.
5. Add API tests with fakes ([10](10_TESTING.md)).
