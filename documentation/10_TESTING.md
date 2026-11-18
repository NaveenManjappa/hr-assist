# 10. Testing

HR Assist has two kinds of checks, and they answer different questions:

| | Tests | Evals |
| --- | --- | --- |
| Question | Does the code work? | How **good** are the answers? |
| Uses | Fakes for OpenAI and Qdrant | The real index and models, plus a judge model |
| Cost | Free | Real money per run |
| Result | Pass or fail | Scores from 0 to 1 that vary a little between runs |
| Runs | On every PR, in CI | By hand ([11](11_EVALS.md)) |

This file is about the tests.

## Running them

Backend, from `backend/`:

```sh
uv run pytest               # all tests, no API keys needed
uv run mypy                 # strict type check of src/ and tests/
uv run ruff check           # lint (E, F, I, UP, B, SIM)
uv run ruff format --check  # formatting, line length 100
```

Frontend, from `frontend/`:

```sh
npm test -- --watch=false   # Vitest, one run
npm run lint                # angular-eslint
npm run build               # the production build must compile
```

## Backend tests

`tests/` mirrors `src/`. There are 87 test functions:

| File | Tests | Level | What it proves |
| --- | --- | --- | --- |
| `api/test_chat.py` | 23 | API through `TestClient`, with fakes | Request rules, each Response Type, Citation building, marker renumbering, snippets, prompt content, history limits, the no-evidence Abstention, `503` mapping |
| `api/test_rate_limit.py` | 13 | API, with `FakeClock` | Each limit and its message, `Retry-After`, per-IP buckets, `X-Forwarded-For` rules, invalid requests not counted, health not limited, the log lines |
| `api/test_health.py` | 6 | API | `ok` and `degraded`, request ID rules, the CORS origin |
| `api/test_errors.py` | 4 | API | One error shape for `422`, `503` and `500`; the cause is logged and hidden |
| `config/test_settings.py` | 5 | Unit | The collection name (and that chunk sizes don't change it); the score threshold's default, environment override and 0 to 1 range |
| `corpus/test_manifest.py` | 2 | Unit | Valid and invalid manifest entries |
| `ingestion/test_pipeline.py` | 25 | Integration, on the **real documents** | Chunking rules against the actual Corpus (see below) |
| `integrations/test_embeddings.py` | 2 | Unit | The embeddings request timeout: 20 seconds by default, or from settings |
| `integrations/test_openai.py` | 7 | Unit | The output token cap, reasoning effort, timeout and retries reach the model |

Test names are full sentences, for example `test_section_3_1_of_the_leave_standard_is_one_chunk_holding_table_3_1`. Read together, they work as a specification.

### The fakes

[tests/conftest.py](../backend/tests/conftest.py) holds the shared fakes. `pyproject.toml` puts `tests/` on the path, so subfolders import them with `from conftest import ...`.

| Fake | Replaces | Lets a test |
| --- | --- | --- |
| `FakeVectorStore` | `QdrantVectorStore` | Set Qdrant up or down for the health check |
| `FakeRetriever` | `QdrantRetriever` | Return fixed chunks, and record the query and `k` |
| `FakeChatModel` | `OpenAIChatModel` | Return a fixed `AssistantReply`, and record the prompt messages it got |
| `FakeClock` | `utc_now` | Move time forward to test minute and day windows |
| `make_chunk(...)` | | Build a valid chunk in one line |
| `settings()` | | Build `Settings` without a `.env` |

They are passed through `create_app(retriever=..., chat_model=..., clock=...)`. This works because the `Answerer` depends on Protocols, not on LangChain classes ([01](01_SYSTEM_OVERVIEW.md)).

### Ingestion tests use the real Corpus

`test_pipeline.py` parses and chunks the real PDFs and decks in `data/policies/`, with no network services. It checks, among others:

- Table 3.1 of the Leave and Absence Standard is one chunk, with its exact rows
- no table is ever split across chunks
- running headers, footers and the superseded banner are removed
- page ranges are right
- contents pages produce no chunks
- deck slides keep their speaker notes
- a manifest entry with the wrong version fails
- `chunking_v2` splits section 3.4 at worked example 3.4b, splits only at unnumbered headings, and repeats a group's heading on later parts
- an overlap as large as the size limit is rejected

So a change to a parser or chunker that breaks a real table fails CI, not just a hand-made example.

**These tests need the internet once per machine.** See [14](14_KNOWN_GOTCHAS.md): `tiktoken` downloads its encoding on first use.

## What CI runs

[.github/workflows/ci.yml](../.github/workflows/ci.yml), on every pull request and every push to `main`. The three jobs run in parallel, and a newer push cancels an older run on the same ref.

| Job | Steps |
| --- | --- |
| `backend` | `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy`, `pytest` |
| `docker` | Build the backend image (not pushed), then `python -c "import hr_assist.api.app"` inside it. This proves the app starts with only the runtime dependencies |
| `frontend` | `npm ci`, `npm run lint`, `npx ng test --watch=false`, `npm run build` |

A successful CI run on `main` triggers the deploy ([13](13_DEPLOYMENT_AND_CI.md)).

## What the tests don't cover

- The real Qdrant and OpenAI calls. No test calls a real service.
- Answer quality. That is what the evals measure ([11](11_EVALS.md)).
- The Docker image at run time, beyond the import check.
- The deploy and ingest workflows. The post-deploy smoke test checks the result instead.

## Writing a new test

- Put it in the folder that mirrors the code under test.
- Name it as a sentence describing the behaviour.
- For API behaviour, build the app with `create_app(settings=..., retriever=FakeRetriever(...), chat_model=FakeChatModel(...))` and call it with `TestClient`.
- Never call real services. If you need a new dependency, define a Protocol for it and add a fake.
- Keep `mypy --strict` passing: tests are type-checked too.
