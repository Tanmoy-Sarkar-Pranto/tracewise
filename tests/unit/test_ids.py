import re

import httpx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tracewise
from tracewise.core.ids import generate_span_id, generate_trace_id
from tracewise.instrumentation.decorators import trace_span

HEX_16 = re.compile(r"^[0-9a-f]{16}$")
HEX_32 = re.compile(r"^[0-9a-f]{32}$")


def test_generate_trace_id_shape():
    trace_id = generate_trace_id()
    assert HEX_32.fullmatch(trace_id)


def test_generate_span_id_shape():
    span_id = generate_span_id()
    assert HEX_16.fullmatch(span_id)


def test_generate_span_id_never_returns_all_zeros(monkeypatch):
    outputs = iter(["0000000000000000", "0123456789abcdef"])
    monkeypatch.setattr("tracewise.core.ids.secrets.token_hex", lambda _: next(outputs))

    span_id = generate_span_id()
    assert span_id == "0123456789abcdef"
    assert span_id != "0000000000000000"


async def test_start_span_uses_w3c_span_id(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "start_span.db"))

    async with tracewise.start_span("work"):
        pass

    span = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])[0]
    assert HEX_32.fullmatch(span.trace_id)
    assert HEX_16.fullmatch(span.span_id)


async def test_middleware_root_span_uses_w3c_span_id(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "middleware.db"))

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")

    span = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])[0]
    assert HEX_16.fullmatch(span.span_id)


async def test_decorator_span_uses_w3c_span_id(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "decorator.db"))

    @trace_span("inner.work")
    async def inner_work():
        return None

    @app.get("/work")
    async def work():
        await inner_work()
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/work")

    spans = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])
    span = next(s for s in spans if s.name == "inner.work")
    assert HEX_16.fullmatch(span.span_id)


async def test_decorator_sync_span_uses_w3c_span_id(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "decorator_sync.db"))

    @trace_span("inner.sync")
    def inner_sync():
        return None

    @app.get("/work")
    async def work():
        inner_sync()
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/work")

    spans = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])
    span = next(s for s in spans if s.name == "inner.sync")
    assert HEX_32.fullmatch(span.trace_id)
    assert HEX_16.fullmatch(span.span_id)


async def test_httpx_client_span_uses_w3c_span_id(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "httpx.db"), instrument_httpx=True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream),
        base_url="http://upstream",
    ) as client:
        await client.get("/ping")

    span = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])[0]
    assert HEX_16.fullmatch(span.span_id)
