# TraceWise

[![PyPI version](https://img.shields.io/pypi/v/tracewise.svg)](https://pypi.org/project/tracewise/)

TraceWise is a small tracing and debugging tool for FastAPI apps.

It records request spans to a local SQLite database and mounts a built-in viewer
at `/tracewise` so you can inspect traces while developing.

Current scope:

- inbound FastAPI request tracing
- manual spans with `tracewise.start_span(...)`
- decorator-based spans with `@tracewise.trace_span(...)`
- span attributes and events
- optional log capture
- optional `httpx` client tracing with `traceparent` propagation
- optional SQLAlchemy DB tracing with raw `db.statement` capture
- local SQLite storage and a minimal embedded UI

This is aimed at local development and debugging. It is not trying to be a full
APM or a hosted tracing backend.

## Install

For local development in this repo:

```bash
uv sync --extra dev
```

Or with `pip`:

```bash
pip install -e .
```

If you want `instrument_httpx=True`, install the optional extra:

```bash
pip install -e ".[httpx]"
```

If you want `instrument_sqlalchemy=True`, install the optional extra:

```bash
pip install -e ".[sqlalchemy]"
```

If you want both optional instrumentations from the Quick Start example:

```bash
pip install -e ".[httpx,sqlalchemy]"
```

For a published package install, the same extra would be:

```bash
pip install "tracewise[httpx]"
```

For a published package install:

```bash
pip install "tracewise[sqlalchemy]"
```

For the published package with both optional instrumentations:

```bash
pip install "tracewise[httpx,sqlalchemy]"
```

## Quick Start

```python
from fastapi import FastAPI
import tracewise

app = FastAPI()

tracewise.init(
    app,
    capture_logs=True,
    instrument_httpx=True,
    instrument_sqlalchemy=True,
)


@app.get("/users")
async def list_users():
    async with tracewise.start_span("db.query", table="users", operation="SELECT"):
        pass

    tracewise.set_attribute("result.count", 2)
    tracewise.add_event("users.loaded")

    return {"users": []}
```

Once the app is running:

- make a request to one of your routes
- open `/tracewise`
- inspect the recorded trace tree

## API Surface

Top-level helpers currently exposed by the package:

- `tracewise.init(app, ...)`
- `tracewise.get_current_span()`
- `tracewise.start_span(name, **attributes)`
- `tracewise.trace_span(name, attributes=...)`
- `tracewise.set_attribute(key, value)`
- `tracewise.set_attributes({...})`
- `tracewise.add_event(name, **attributes)`

Main `init()` options:

- `db_path`: path to the SQLite database file
- `max_traces`: max number of traces to keep
- `enabled`: turn tracing on or off
- `capture_logs`: attach a logging handler that records log events on the
  active span
- `instrument_httpx`: record outbound `httpx` requests and inject
  `traceparent` headers
- `instrument_sqlalchemy`: record SQLAlchemy statements as DB `CLIENT` spans
  and capture raw `db.statement` text without parameter payloads

If `db_path` is not provided, TraceWise stores data under
`~/.tracewise/traces.db`.

You can also disable tracing with:

```bash
TRACEWISE_ENABLED=false
```

## Example App

A small example app lives in `tests/testapp/main.py`.

To run it with Docker:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Then open:

- `http://localhost:8000/health`
- `http://localhost:8000/users`
- `http://localhost:8000/db-users`
- `http://localhost:8000/orders`
- `http://localhost:8000/error`
- `http://localhost:8000/tracewise`

To generate DB spans in the demo app:

```bash
curl http://localhost:8000/db-users
curl -X POST http://localhost:8000/db-users \
  -H "Content-Type: application/json" \
  -d '{"name":"Charlie"}'
```

## Current Limitations

- FastAPI-specific for now
- local SQLite storage only
- viewer UI is intentionally minimal
- `httpx` tracing is optional and only applies if your app uses `httpx`
- not a replacement for OpenTelemetry or a hosted tracing stack

## Development

Run the tests with:

```bash
uv run pytest
```
