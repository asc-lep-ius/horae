# --- Stage 1: builder ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# --- Stage 2: runtime ---
FROM python:3.12-slim

RUN groupadd --system horae && useradd --system --gid horae horae

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER horae

CMD ["uvicorn", "horae.app:app", "--host", "0.0.0.0", "--port", "8000"]
