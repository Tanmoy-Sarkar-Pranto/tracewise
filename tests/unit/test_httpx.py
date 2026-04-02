import httpx
import pytest
import re
from fastapi import FastAPI
from fastapi import Request

import tracewise
from tracewise.core.models import SpanKind, SpanStatus
from tracewise.instrumentation import httpx as tracewise_httpx

TRACEPARENT_RE = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-01$")


def parse_traceparent(value: str) -> tuple[str, str, str, str]:
    version, trace_id, parent_id, flags = value.split("-")
    return version, trace_id, parent_id, flags


def test_httpx_patch_is_not_installed_when_opted_out(tmp_path):
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    app = FastAPI()

    tracewise.init(app, db_path=str(tmp_path / "opt_out_unpatched.db"), instrument_httpx=False)

    assert httpx.AsyncClient.send is original_async_send
    assert httpx.Client.send is original_sync_send


async def test_httpx_instrumentation_is_opt_in(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "opt_in.db"))

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://upstream",
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    assert len(spans) == 1
    assert spans[0].name == "parent.work"
    assert spans[0].kind != SpanKind.CLIENT


async def test_async_httpx_creates_child_client_span(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_child.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://upstream",
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    parent = next(span for span in spans if span.name == "parent.work")
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)

    assert child.parent_span_id == parent.span_id
    assert child.name == "HTTP GET upstream"
    assert child.status == SpanStatus.OK
    assert child.attributes["http.method"] == "GET"
    assert child.attributes["http.url"] == "http://upstream/ping"
    assert child.attributes["http.status_code"] == 200
    assert child.attributes["http.client_library"] == "httpx"
    assert child.attributes["http.client_class"] == "AsyncClient"


async def test_async_httpx_without_parent_creates_root_client_trace(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_root.db"), instrument_httpx=True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream),
        base_url="http://api.example.test",
    ) as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)

    assert len(spans) == 1
    span = spans[0]
    assert span.parent_span_id is None
    assert span.kind == SpanKind.CLIENT
    assert span.name == "HTTP GET api.example.test"
    assert span.attributes["http.client_class"] == "AsyncClient"


async def test_sync_httpx_creates_child_client_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "sync_child.db"), instrument_httpx=True)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(204, request=request)
    )

    async with tracewise.start_span("parent.work") as parent:
        with httpx.Client(
            transport=transport,
            base_url="https://sync.example.test",
        ) as client:
            response = client.get("/health")

    assert response.status_code == 204
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)

    assert child.parent_span_id == parent.span_id
    assert child.name == "HTTP GET sync.example.test"
    assert child.status == SpanStatus.OK
    assert child.attributes["http.method"] == "GET"
    assert child.attributes["http.url"] == "https://sync.example.test/health"
    assert child.attributes["http.status_code"] == 204
    assert child.attributes["http.client_class"] == "Client"


def test_sync_httpx_creates_root_client_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "sync_root.db"), instrument_httpx=True)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(204, request=request)
    )

    with httpx.Client(
        transport=transport,
        base_url="https://sync.example.test",
    ) as client:
        response = client.get("/health")

    assert response.status_code == 204
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)

    assert len(spans) == 1
    span = spans[0]
    assert span.parent_span_id is None
    assert span.kind == SpanKind.CLIENT
    assert span.name == "HTTP GET sync.example.test"
    assert span.status == SpanStatus.OK
    assert span.attributes["http.url"] == "https://sync.example.test/health"
    assert span.attributes["http.status_code"] == 204
    assert span.attributes["http.client_class"] == "Client"


async def test_async_httpx_error_records_exception_and_restores_parent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/boom")
    async def boom():
        raise RuntimeError("upstream boom")

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_error.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work") as parent:
        with pytest.raises(RuntimeError, match="upstream boom"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=upstream),
                base_url="http://upstream",
            ) as client:
                await client.get("/boom")

        assert tracewise.get_current_span() is parent

    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)

    assert child.status == SpanStatus.ERROR
    assert child.attributes["error.message"] == "upstream boom"
    assert child.end_time is not None
    assert len(child.events) == 1
    assert child.events[0].name == "exception"
    assert child.events[0].attributes["exception.type"] == "RuntimeError"
    assert child.events[0].attributes["exception.message"] == "upstream boom"


async def test_httpx_instrumentation_is_idempotent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app1 = FastAPI()
    tracewise.init(app1, db_path=str(tmp_path / "idempotent.db"), instrument_httpx=True)

    app2 = FastAPI()
    tracewise.init(app2, db_path=str(tmp_path / "idempotent.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://upstream",
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    client_spans = [span for span in spans if span.kind == SpanKind.CLIENT]
    assert len(client_spans) == 1


async def test_async_httpx_injects_traceparent_from_client_span(tmp_path):
    upstream = FastAPI()

    @upstream.get("/headers")
    async def headers(request: Request):
        return {"traceparent": request.headers.get("traceparent")}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_traceparent.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="https://upstream.test",
        ) as client:
            response = await client.get("/headers")

    header = response.json()["traceparent"]
    assert TRACEPARENT_RE.fullmatch(header)

    spans = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)
    version, trace_id, parent_id, flags = parse_traceparent(header)

    assert version == "00"
    assert trace_id == child.trace_id
    assert parent_id == child.span_id
    assert flags == "01"


def test_sync_httpx_root_request_injects_traceparent(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "sync_traceparent.db"), instrument_httpx=True)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"traceparent": request.headers.get("traceparent")},
            request=request,
        )
    )

    with httpx.Client(
        transport=transport,
        base_url="https://sync.example.test",
    ) as client:
        response = client.get("/headers")

    header = response.json()["traceparent"]
    assert TRACEPARENT_RE.fullmatch(header)

    span = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])[0]
    version, trace_id, parent_id, flags = parse_traceparent(header)

    assert version == "00"
    assert trace_id == span.trace_id
    assert parent_id == span.span_id
    assert flags == "01"


async def test_httpx_preserves_existing_traceparent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/headers")
    async def headers(request: Request):
        return {"traceparent": request.headers.get("traceparent")}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "preserve_valid.db"), instrument_httpx=True)

    existing = "00-11111111111111111111111111111111-2222222222222222-01"

    async with tracewise.start_span("parent.work") as parent:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="https://upstream.test",
        ) as client:
            response = await client.get("/headers", headers={"traceparent": existing})

    assert response.json()["traceparent"] == existing
    spans = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)
    assert child.parent_span_id == parent.span_id


def test_sync_httpx_preserves_existing_traceparent_and_records_local_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "preserve_valid_sync.db"), instrument_httpx=True)

    existing = "00-11111111111111111111111111111111-2222222222222222-01"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"traceparent": request.headers.get("traceparent")},
            request=request,
        )
    )

    with httpx.Client(
        transport=transport,
        base_url="https://sync.example.test",
    ) as client:
        response = client.get("/headers", headers={"traceparent": existing})

    assert response.json()["traceparent"] == existing
    spans = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])
    assert any(span.kind == SpanKind.CLIENT for span in spans)


async def test_httpx_preserves_malformed_traceparent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/headers")
    async def headers(request: Request):
        return {"traceparent": request.headers.get("traceparent")}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "preserve_bad.db"), instrument_httpx=True)

    malformed = "not-a-valid-traceparent"

    async with tracewise.start_span("parent.work") as parent:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="https://upstream.test",
        ) as client:
            response = await client.get("/headers", headers={"traceparent": malformed})

    assert response.json()["traceparent"] == malformed
    spans = tracewise._storage.get_trace(tracewise._storage.list_traces()[0])
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)
    assert child.parent_span_id == parent.span_id


async def test_httpx_opt_out_does_not_inject_traceparent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/headers")
    async def headers(request: Request):
        return {"traceparent": request.headers.get("traceparent")}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "no_traceparent.db"), instrument_httpx=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream),
        base_url="https://upstream.test",
    ) as client:
        response = await client.get("/headers")

    assert response.json()["traceparent"] is None


def test_httpx_reset_unpatches_client_and_asyncclient_send(tmp_path):
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "patched_then_reset.db"), instrument_httpx=True)

    assert httpx.AsyncClient.send is not original_async_send
    assert httpx.Client.send is not original_sync_send
    tracewise_httpx.reset_httpx_instrumentation()
    assert httpx.AsyncClient.send is original_async_send
    assert httpx.Client.send is original_sync_send
