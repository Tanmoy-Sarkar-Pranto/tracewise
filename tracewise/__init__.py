from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI

from tracewise.core.context import get_current_span as _get_current_span
from tracewise.core.context import reset_span, set_current_span
from tracewise.core.models import Span, SpanEvent, SpanKind, SpanStatus
from tracewise.instrumentation import decorators as _decorators
from tracewise.instrumentation.middleware import _record_exception

_storage = None


def init(
    app: FastAPI,
    *,
    db_path: str | None = None,
    max_traces: int = 1000,
    enabled: bool = True,
    capture_logs: bool | int = False,
) -> None:
    import os
    env_enabled = os.environ.get("TRACEWISE_ENABLED", "true").lower() not in ("false", "0", "no")
    if not (enabled and env_enabled):
        return

    global _storage

    from tracewise.storage.sqlite import SQLiteStorage
    from tracewise.instrumentation.middleware import TraceWiseMiddleware
    from tracewise.viewer.app import create_viewer_app

    if db_path is None:
        db_path = str(Path.home() / ".tracewise" / "traces.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _storage = SQLiteStorage(db_path=db_path, max_traces=max_traces)
    _decorators._storage = _storage

    app.add_middleware(TraceWiseMiddleware, storage=_storage, skip_prefixes=["/tracewise"])

    viewer = create_viewer_app(storage=_storage)
    app.mount("/tracewise", viewer)

    if capture_logs is not False:
        import logging
        from tracewise.instrumentation.logging import TraceWiseLogHandler
        level = logging.NOTSET if capture_logs is True else capture_logs
        handler = TraceWiseLogHandler(level=level)
        logging.getLogger().addHandler(handler)


def get_current_span() -> Span | None:
    return _get_current_span()


def set_attribute(key: str, value) -> None:
    span = _get_current_span()
    if span is not None:
        span.attributes[key] = value


def set_attributes(attrs: dict) -> None:
    span = _get_current_span()
    if span is not None:
        span.attributes.update(attrs)


def add_event(name: str, **attributes) -> None:
    from datetime import datetime, timezone
    span = _get_current_span()
    if span is not None:
        span.events.append(SpanEvent(
            name=name,
            timestamp=datetime.now(timezone.utc),
            attributes=attributes,
        ))


@asynccontextmanager
async def start_span(name: str, **attributes) -> AsyncIterator[Span]:
    if _storage is None:
        yield None
        return

    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    parent = _get_current_span()
    span = Span(
        trace_id=parent.trace_id if parent else uuid4().hex,
        span_id=uuid4().hex,
        parent_span_id=parent.span_id if parent else None,
        name=name,
        kind=SpanKind.INTERNAL,
        start_time=_utcnow(),
        end_time=None,
        status=SpanStatus.UNSET,
        attributes=dict(attributes),
    )
    _storage.save_span(span)
    token = set_current_span(span)
    try:
        yield span
        span.status = SpanStatus.OK
    except Exception as exc:
        span.status = SpanStatus.ERROR
        span.attributes["error.message"] = str(exc)
        _record_exception(span, exc)
        raise
    finally:
        span.end_time = _utcnow()
        _storage.update_span(span)
        reset_span(token)


from tracewise.instrumentation.decorators import trace_span  # noqa: E402

__all__ = ["init", "get_current_span", "start_span", "trace_span",
           "set_attribute", "set_attributes", "add_event"]
