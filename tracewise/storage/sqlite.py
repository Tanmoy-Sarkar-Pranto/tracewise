from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tracewise.core.models import Span, SpanEvent, SpanKind, SpanStatus
from tracewise.storage.base import BaseStorage

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spans (
    span_id        TEXT PRIMARY KEY,
    trace_id       TEXT NOT NULL,
    parent_span_id TEXT,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL,
    start_time     TEXT NOT NULL,
    end_time       TEXT,
    status         TEXT NOT NULL,
    attributes     TEXT,
    events         TEXT,
    meta           TEXT
);
CREATE INDEX IF NOT EXISTS idx_trace_id   ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_start_time ON spans(start_time);
"""


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _row_to_span(row: dict) -> Span:
    events_raw = json.loads(row["events"] or "[]")
    events = [
        SpanEvent(
            name=e["name"],
            timestamp=_parse_dt(e["timestamp"]),
            attributes=e.get("attributes", {}),
        )
        for e in events_raw
    ]
    return Span(
        trace_id=row["trace_id"],
        span_id=row["span_id"],
        parent_span_id=row["parent_span_id"],
        name=row["name"],
        kind=SpanKind(row["kind"]),
        start_time=_parse_dt(row["start_time"]),
        end_time=_parse_dt(row["end_time"]),
        status=SpanStatus(row["status"]),
        attributes=json.loads(row["attributes"] or "{}"),
        events=events,
        _meta=json.loads(row["meta"] or "{}"),
    )


class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str | Path = ":memory:", max_traces: int = 1000):
        self._max_traces = max_traces
        self._local = threading.local()
        raw_db_path = str(db_path)

        # A named shared-cache memory database lets per-thread connections
        # see the same state while keeping the database alive via _anchor_conn.
        if raw_db_path == ":memory:":
            self._db_path = f"file:tracewise-{uuid4().hex}?mode=memory&cache=shared"
            self._use_uri = True
        else:
            self._db_path = raw_db_path
            self._use_uri = raw_db_path.startswith("file:")

        self._anchor_conn = self._connect()
        self._anchor_conn.executescript(_CREATE_TABLE)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,
            timeout=30,
            uri=self._use_uri,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    def save_span(self, span: Span) -> None:
        conn = self._get_conn()
        events_json = json.dumps([
            {"name": e.name, "timestamp": _fmt_dt(e.timestamp), "attributes": e.attributes}
            for e in span.events
        ])
        conn.execute(
            """
            INSERT INTO spans
                (span_id, trace_id, parent_span_id, name, kind,
                 start_time, end_time, status, attributes, events, meta)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                span.span_id, span.trace_id, span.parent_span_id,
                span.name, span.kind.value,
                _fmt_dt(span.start_time), _fmt_dt(span.end_time),
                span.status.value,
                json.dumps(span.attributes),
                events_json,
                json.dumps(span._meta),
            ),
        )
        self.delete_old_traces(keep=self._max_traces)

    def update_span(self, span: Span) -> None:
        conn = self._get_conn()
        events_json = json.dumps([
            {"name": e.name, "timestamp": _fmt_dt(e.timestamp), "attributes": e.attributes}
            for e in span.events
        ])
        conn.execute(
            """
            UPDATE spans SET
                end_time=?, status=?, attributes=?, events=?, meta=?
            WHERE span_id=?
            """,
            (
                _fmt_dt(span.end_time),
                span.status.value,
                json.dumps(span.attributes),
                events_json,
                json.dumps(span._meta),
                span.span_id,
            ),
        )

    def get_trace(self, trace_id: str) -> list[Span]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM spans WHERE trace_id=? ORDER BY start_time",
            (trace_id,),
        ).fetchall()
        return [_row_to_span(dict(row)) for row in rows]

    def list_traces(self, limit: int = 50) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT trace_id, MAX(start_time) as latest
            FROM spans
            GROUP BY trace_id
            ORDER BY latest DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["trace_id"] for row in rows]

    def delete_old_traces(self, keep: int) -> None:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT trace_id FROM (
                SELECT trace_id, MAX(start_time) as latest
                FROM spans GROUP BY trace_id
                ORDER BY latest DESC
            ) LIMIT -1 OFFSET ?
            """,
            (keep,),
        ).fetchall()
        for row in rows:
            conn.execute("DELETE FROM spans WHERE trace_id=?", (row["trace_id"],))

    def clear(self) -> None:
        self._get_conn().execute("DELETE FROM spans")
