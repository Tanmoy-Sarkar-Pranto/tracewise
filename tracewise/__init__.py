from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import AsyncIterator

from fastapi import FastAPI

from tracewise.core.context import get_current_span as _get_current_span
from tracewise.core.context import reset_span, set_current_span
from tracewise.core.ids import generate_span_id, generate_trace_id
from tracewise.core.models import Span, SpanEvent, SpanKind, SpanStatus
from tracewise.instrumentation import decorators as _decorators
from tracewise.instrumentation.middleware import _record_exception

_storage = None
_httpx_instrumentation_enabled = False
_APP_STORAGE_ATTR = "_tracewise_storage"
_VIEWER_MOUNT_PATH = "/tracewise"


def _reset_httpx_instrumentation_if_loaded() -> None:
    module = sys.modules.get("tracewise.instrumentation.httpx")
    if module is None:
        return
    module.reset_httpx_instrumentation()


def _get_or_create_app_storage(app: FastAPI, db_path: str | None, max_traces: int):
    storage = getattr(app.state, _APP_STORAGE_ATTR, None)
    if storage is not None:
        return storage

    if db_path is None:
        db_path = str(Path.home() / ".tracewise" / "traces.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    from tracewise.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(db_path=db_path, max_traces=max_traces)
    setattr(app.state, _APP_STORAGE_ATTR, storage)
    return storage


def _app_has_tracewise_middleware(app: FastAPI) -> bool:
    from tracewise.instrumentation.middleware import TraceWiseMiddleware

    return any(getattr(middleware, "cls", None) is TraceWiseMiddleware for middleware in app.user_middleware)


def _app_has_tracewise_viewer_mount(app: FastAPI) -> bool:
    return any(getattr(route, "path", None) == _VIEWER_MOUNT_PATH for route in app.routes)


def _ensure_log_handler(level: int) -> None:
    from tracewise.instrumentation.logging import TraceWiseLogHandler

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, TraceWiseLogHandler):
            handler.setLevel(level)
            return

    root_logger.addHandler(TraceWiseLogHandler(level=level))


def init(
    app: FastAPI,
    *,
    db_path: str | None = None,
    max_traces: int = 1000,
    enabled: bool = True,
    capture_logs: bool | int = False,
    instrument_httpx: bool = False,
) -> None:
    global _storage, _httpx_instrumentation_enabled

    import os
    env_enabled = os.environ.get("TRACEWISE_ENABLED", "true").lower() not in ("false", "0", "no")
    if not (enabled and env_enabled):
        _storage = None
        _decorators._storage = None
        _httpx_instrumentation_enabled = False
        _reset_httpx_instrumentation_if_loaded()
        return

    from tracewise.instrumentation.middleware import TraceWiseMiddleware
    from tracewise.viewer.app import create_viewer_app

    install_httpx_instrumentation = None
    if instrument_httpx:
        from tracewise.instrumentation.httpx import install_httpx_instrumentation

    _storage = _get_or_create_app_storage(app, db_path, max_traces)
    _httpx_instrumentation_enabled = instrument_httpx
    _decorators._storage = _storage

    if not _app_has_tracewise_middleware(app):
        app.add_middleware(TraceWiseMiddleware, storage=_storage, skip_prefixes=[_VIEWER_MOUNT_PATH])

    if not _app_has_tracewise_viewer_mount(app):
        viewer = create_viewer_app(storage=_storage)
        app.mount(_VIEWER_MOUNT_PATH, viewer)

    if capture_logs is not False:
        level = logging.NOTSET if capture_logs is True else capture_logs
        _ensure_log_handler(level)

    if instrument_httpx:
        install_httpx_instrumentation(
            should_trace_httpx=lambda: _httpx_instrumentation_enabled,
            get_storage=lambda: _storage,
        )
    else:
        _reset_httpx_instrumentation_if_loaded()


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
        trace_id=parent.trace_id if parent else generate_trace_id(),
        span_id=generate_span_id(),
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
