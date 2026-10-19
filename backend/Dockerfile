# The backend API image (docs/deployment.md D12). Build from the repo root:
#   docker build -f backend/Dockerfile -t hr-assist-api .
# Runtime dependencies only: no dev group, and no ingest group, so no PDF or PPTX libraries.

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /src

# Dependencies first, so code changes don't reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-group ingest --no-install-project

COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-group ingest --no-editable


FROM python:3.13-slim

RUN useradd --system --uid 10001 --no-create-home app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

USER app
EXPOSE 8080

# Cloud Run sets PORT; exec so uvicorn receives SIGTERM directly.
CMD ["sh", "-c", "exec uvicorn hr_assist.api.app:create_app --factory --host 0.0.0.0 --port \"${PORT:-8080}\""]
