import asyncio

import anyio
import pytest
import time
from datetime import datetime, timezone
from tracewise.core.models import Span, SpanEvent, SpanKind, SpanStatus
from tracewise.storage.sqlite import SQLiteStorage


def utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=tmp_path / "test.db")


def test_save_and_retrieve_span(storage, make_span):
    span = make_span(trace_id="t1", span_id="s1")
    storage.save_span(span)
    spans = storage.get_trace("t1")
    assert len(spans) == 1
    assert spans[0].span_id == "s1"
    assert spans[0].trace_id == "t1"
    assert spans[0].name == "GET /test"


def test_update_span_end_time(storage, make_span):
    span = make_span(trace_id="t1", span_id="s1", end_time=None)
    storage.save_span(span)
    span.end_time = utcnow()
    span.status = SpanStatus.OK
    storage.update_span(span)
    spans = storage.get_trace("t1")
    assert spans[0].end_time is not None
    assert spans[0].status == SpanStatus.OK


def test_attributes_round_trip(storage, make_span):
    span = make_span(trace_id="t1", span_id="s1")
    span.attributes = {"http.method": "GET", "http.status_code": 200}
    storage.save_span(span)
    spans = storage.get_trace("t1")
    assert spans[0].attributes["http.method"] == "GET"
    assert spans[0].attributes["http.status_code"] == 200


def test_events_round_trip(storage, make_span):
    span = make_span(trace_id="t1", span_id="s1")
    span.events = [SpanEvent(name="cache.miss", timestamp=utcnow(), attributes={"key": "users"})]
    storage.save_span(span)
    spans = storage.get_trace("t1")
    assert len(spans[0].events) == 1
    assert spans[0].events[0].name == "cache.miss"
    assert spans[0].events[0].attributes["key"] == "users"


def test_list_traces_returns_trace_ids(storage, make_span):
    storage.save_span(make_span(trace_id="t1", span_id="s1"))
    storage.save_span(make_span(trace_id="t2", span_id="s2"))
    traces = storage.list_traces(limit=10)
    assert set(traces) == {"t1", "t2"}


def test_list_traces_respects_limit(storage, make_span):
    for i in range(5):
        storage.save_span(make_span(trace_id=f"t{i}", span_id=f"s{i}"))
    traces = storage.list_traces(limit=3)
    assert len(traces) == 3


def test_get_trace_returns_empty_for_unknown(storage):
    assert storage.get_trace("nonexistent") == []


def test_clear_removes_all_spans(storage, make_span):
    storage.save_span(make_span(trace_id="t1", span_id="s1"))
    storage.save_span(make_span(trace_id="t2", span_id="s2"))
    storage.clear()
    assert storage.list_traces(limit=10) == []


def test_delete_old_traces_keeps_newest(storage, make_span):
    for i in range(4):
        storage.save_span(make_span(trace_id=f"t{i}", span_id=f"s{i}"))
        time.sleep(0.01)
    storage.delete_old_traces(keep=2)
    remaining = storage.list_traces(limit=10)
    assert len(remaining) == 2


async def test_storage_methods_work_from_worker_thread(storage, make_span):
    storage.save_span(make_span(trace_id="t1", span_id="s1"))

    traces = await asyncio.wait_for(
        anyio.to_thread.run_sync(storage.list_traces, 10),
        timeout=2,
    )
    spans = await asyncio.wait_for(
        anyio.to_thread.run_sync(storage.get_trace, "t1"),
        timeout=2,
    )

    assert traces == ["t1"]
    assert len(spans) == 1
    assert spans[0].span_id == "s1"
