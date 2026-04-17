# Horae

Natural language calendar event creation — a self-hosted FastAPI endpoint that parses spoken or typed event descriptions into CalDAV events on Radicale.

## Architecture

```
Tasker → Tailscale → Horae (FastAPI) → dateparser / Ollama → Radicale (CalDAV)
```

Text input is first attempted with `dateparser` (fast, offline). If that fails,
Horae falls back to a local Ollama LLM for extraction. Parsed events are pushed
to Radicale over CalDAV.

## Quick Start

```bash
cp .env.example .env        # edit with your Radicale credentials
docker compose up -d         # builds and starts Horae on :8000
curl http://localhost:8000/health
```

## API

### `POST /events` — Create event from natural language

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"text": "Dentist appointment tomorrow at 3pm"}'
```

Response `201`: `{"summary": "Dentist appointment", "dtstart": "2026-04-01T15:00:00", "dtend": "2026-04-01T16:00:00", "calendar": "personal", "uid": "a1b2c3d4-..."}`

### `GET /calendars` — List Radicale calendars

Response `200`: `[{"name": "personal", "path": "/asclepius/personal/"}]`

### `GET /health`

Response `200`: `{"status": "ok"}`

## Configuration

All settings are read from environment variables (prefix `HORAE_`):

| Variable | Default | Description |
|---|---|---|
| `HORAE_RADICALE_URL` | `http://localhost:5232` | Radicale server URL |
| `HORAE_RADICALE_USERNAME` | *(required)* | CalDAV username |
| `HORAE_RADICALE_PASSWORD` | *(required)* | CalDAV password |
| `HORAE_DEFAULT_CALENDAR` | `personal` | Calendar to use when none specified |
| `HORAE_DEFAULT_DURATION_MINUTES` | `60` | Default event length in minutes |
| `HORAE_OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `HORAE_OLLAMA_MODEL` | `llama3.2` | Model for LLM fallback parsing |

## Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
make install      # uv sync (installs all deps including dev)
make test         # pytest
make lint         # ruff check
make format       # ruff format
make typecheck    # pyright
make run          # uvicorn with --reload on :8000
```
