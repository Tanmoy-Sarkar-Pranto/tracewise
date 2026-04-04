from __future__ import annotations

import builtins

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

import tracewise
from tracewise.core.models import SpanKind, SpanStatus


def _trace_spans() -> list:
    trace_ids = tracewise._storage.list_traces(limit=10)
    assert len(trace_ids) == 1
    return tracewise._storage.get_trace(trace_ids[0])


def _db_spans(spans: list) -> list:
    return [
        span
        for span in spans
        if span.kind == SpanKind.CLIENT and "db.statement" in span.attributes
    ]


async def test_sync_sqlalchemy_creates_child_db_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}")

    async with tracewise.start_span("parent.work") as parent:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))

        assert tracewise.get_current_span() is parent

    spans = _trace_spans()
    parent_span = next(span for span in spans if span.name == "parent.work")
    child = _db_spans(spans)[0]

    assert child.parent_span_id == parent_span.span_id
    assert child.name == "SQL SELECT"
    assert child.status == SpanStatus.OK
    assert child.attributes["db.system"] == "sqlite"
    assert child.attributes["db.operation"] == "SELECT"
    assert child.attributes["db.statement"] == "SELECT 1"
    assert child.attributes["db.executemany"] is False


def test_sqlalchemy_without_active_span_creates_no_trace(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_engine(f"sqlite:///{tmp_path / 'noparent.db'}")

    with engine.begin() as conn:
        conn.execute(text("SELECT 1"))

    assert tracewise._storage.list_traces(limit=10) == []


async def test_sync_sqlalchemy_insert_records_rowcount_and_raw_sql(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_engine(f"sqlite:///{tmp_path / 'rowcount.db'}")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))

    async with tracewise.start_span("parent.work"):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO items (name) VALUES (:name)"),
                {"name": "widget"},
            )

    child = _db_spans(_trace_spans())[0]

    assert child.name == "SQL INSERT"
    assert child.attributes["db.statement"] == "INSERT INTO items (name) VALUES (?)"
    assert "widget" not in child.attributes["db.statement"]
    assert child.attributes["db.rowcount"] == 1


async def test_sqlalchemy_operation_ignores_leading_comments(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_engine(f"sqlite:///{tmp_path / 'comments.db'}")

    async with tracewise.start_span("parent.work"):
        with engine.begin() as conn:
            conn.execute(text("/* tracewise */ SELECT 1"))

    child = _db_spans(_trace_spans())[0]

    assert child.name == "SQL SELECT"
    assert child.attributes["db.operation"] == "SELECT"
    assert child.attributes["db.statement"] == "/* tracewise */ SELECT 1"


async def test_sync_sqlalchemy_error_records_exception_event(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_engine(f"sqlite:///{tmp_path / 'error.db'}")

    async with tracewise.start_span("parent.work") as parent:
        with pytest.raises(OperationalError, match="no such table"):
            with engine.begin() as conn:
                conn.execute(text("SELECT * FROM missing_table"))

        assert tracewise.get_current_span() is parent

    child = _db_spans(_trace_spans())[0]

    assert child.status == SpanStatus.ERROR
    assert "no such table" in child.attributes["error.message"]
    assert child.events[0].name == "exception"
    assert child.events[0].attributes["exception.type"] == "OperationalError"
    assert "no such table" in child.events[0].attributes["exception.message"]


async def test_async_sqlalchemy_creates_child_db_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'async.db'}")

    try:
        async with tracewise.start_span("parent.work") as parent:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))

            assert tracewise.get_current_span() is parent

        spans = _trace_spans()
        parent_span = next(span for span in spans if span.name == "parent.work")
        child = _db_spans(spans)[0]

        assert child.parent_span_id == parent_span.span_id
        assert child.name == "SQL SELECT"
        assert child.status == SpanStatus.OK
        assert child.attributes["db.system"] == "sqlite"
        assert child.attributes["db.statement"] == "SELECT 1"
    finally:
        await engine.dispose()


async def test_async_sqlalchemy_insert_records_rowcount(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'async-rowcount.db'}")

    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))

        async with tracewise.start_span("parent.work"):
            async with engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO items (name) VALUES (:name)"),
                    {"name": "widget"},
                )

        child = _db_spans(_trace_spans())[0]
        assert child.attributes["db.statement"] == "INSERT INTO items (name) VALUES (?)"
        assert child.attributes["db.rowcount"] == 1
    finally:
        await engine.dispose()


async def test_sqlalchemy_instrumentation_is_idempotent(tmp_path):
    first_app = FastAPI()
    tracewise.init(first_app, db_path=str(tmp_path / "first.db"), instrument_sqlalchemy=True)

    second_app = FastAPI()
    tracewise.init(second_app, db_path=str(tmp_path / "second.db"), instrument_sqlalchemy=True)

    engine = create_engine(f"sqlite:///{tmp_path / 'idem.db'}")

    async with tracewise.start_span("parent.work"):
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = _db_spans(_trace_spans())
    assert len(db_spans) == 1


async def test_sqlalchemy_finish_bookkeeping_failure_does_not_break_query_or_parent(tmp_path, monkeypatch):
    from tracewise.instrumentation import sqlalchemy as tracewise_sqlalchemy

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)
    engine = create_engine(f"sqlite:///{tmp_path / 'finish-fail.db'}")

    real_utcnow = tracewise_sqlalchemy._utcnow
    calls = {"count": 0}

    def fail_on_finish():
        calls["count"] += 1
        if calls["count"] >= 2:
            raise RuntimeError("finish bookkeeping failure")
        return real_utcnow()

    monkeypatch.setattr(tracewise_sqlalchemy, "_utcnow", fail_on_finish)

    async with tracewise.start_span("parent.work") as parent:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
        assert tracewise.get_current_span() is parent


async def test_sqlalchemy_context_state_failure_does_not_leak_or_break_query(tmp_path, monkeypatch):
    from tracewise.instrumentation import sqlalchemy as tracewise_sqlalchemy

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)
    engine = create_engine(f"sqlite:///{tmp_path / 'state-fail.db'}")

    original_setattr = builtins.setattr

    def fail_state_attach(obj, name, value):
        if name == tracewise_sqlalchemy._STATE_ATTR:
            raise RuntimeError("state attach failure")
        return original_setattr(obj, name, value)

    monkeypatch.setattr(builtins, "setattr", fail_state_attach)

    async with tracewise.start_span("parent.work") as parent:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
        assert tracewise.get_current_span() is parent

    assert _db_spans(_trace_spans()) == []


async def test_sqlalchemy_save_failure_does_not_break_query_or_parent(tmp_path, monkeypatch):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "trace.db"), instrument_sqlalchemy=True)
    engine = create_engine(f"sqlite:///{tmp_path / 'save-fail.db'}")

    original_save_span = tracewise._storage.save_span

    def fail_db_save(span):
        if span.kind == SpanKind.CLIENT:
            raise RuntimeError("save failure")
        return original_save_span(span)

    monkeypatch.setattr(tracewise._storage, "save_span", fail_db_save)

    async with tracewise.start_span("parent.work") as parent:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
        assert tracewise.get_current_span() is parent

    assert _db_spans(_trace_spans()) == []
