from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.ids import generate_span_id
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.instrumentation.middleware import _record_exception
from tracewise.storage.base import BaseStorage

_should_trace_sqlalchemy: Callable[[], bool] = lambda: False
_get_storage: Callable[[], BaseStorage | None] = lambda: None
_event = None
_Engine = None
_installed = False
_STATE_ATTR = "_tracewise_span_state"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_operation(statement: str) -> str:
    stripped = statement.lstrip()
    while stripped.startswith("/*"):
        closing = stripped.find("*/")
        if closing == -1:
            return "QUERY"
        stripped = stripped[closing + 2 :].lstrip()
    while stripped.startswith("--"):
        newline = stripped.find("\n")
        if newline == -1:
            return "QUERY"
        stripped = stripped[newline + 1 :].lstrip()
    if not stripped:
        return "QUERY"
    return stripped.split(None, 1)[0].upper()


def _build_db_span(statement: str, conn, executemany: bool) -> Span | None:
    parent = get_current_span()
    if parent is None:
        return None

    operation = _extract_operation(statement)
    return Span(
        trace_id=parent.trace_id,
        span_id=generate_span_id(),
        parent_span_id=parent.span_id,
        name=f"SQL {operation}",
        kind=SpanKind.CLIENT,
        start_time=_utcnow(),
        end_time=None,
        status=SpanStatus.UNSET,
        attributes={
            "db.system": conn.engine.dialect.name,
            "db.operation": operation,
            "db.statement": statement,
            "db.executemany": bool(executemany),
        },
    )


def _finish_sql_span(context, *, cursor=None, exc=None) -> None:
    state = getattr(context, _STATE_ATTR, None)
    if state is None:
        return

    try:
        delattr(context, _STATE_ATTR)
    except Exception:
        pass

    try:
        storage, span, token = state
    except Exception:
        return

    try:
        if exc is None:
            span.status = SpanStatus.OK
            rowcount = getattr(cursor, "rowcount", None)
            if rowcount is not None and rowcount >= 0:
                span.attributes["db.rowcount"] = rowcount
        else:
            span.status = SpanStatus.ERROR
            span.attributes["error.message"] = str(exc)
            _record_exception(span, exc)

        span.end_time = _utcnow()
        storage.update_span(span)
    except Exception:
        return
    finally:
        try:
            reset_span(token)
        except Exception:
            pass


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    try:
        if not _should_trace_sqlalchemy():
            return

        storage = _get_storage()
        if storage is None:
            return

        span = _build_db_span(statement, conn, executemany)
        if span is None:
            return

        token = set_current_span(span)
        try:
            setattr(context, _STATE_ATTR, (storage, span, token))
        except Exception:
            reset_span(token)
            return

        try:
            storage.save_span(span)
        except Exception:
            try:
                delattr(context, _STATE_ATTR)
            except Exception:
                pass
            reset_span(token)
    except Exception:
        return


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    try:
        _finish_sql_span(context, cursor=cursor)
    except Exception:
        return


def _handle_error(exception_context):
    try:
        context = exception_context.execution_context
        if context is None:
            return
        _finish_sql_span(context, exc=exception_context.original_exception)
    except Exception:
        return


def install_sqlalchemy_instrumentation(
    *,
    should_trace_sqlalchemy: Callable[[], bool],
    get_storage: Callable[[], BaseStorage | None],
) -> None:
    global _should_trace_sqlalchemy, _get_storage, _event, _Engine, _installed

    _should_trace_sqlalchemy = should_trace_sqlalchemy
    _get_storage = get_storage

    if _installed:
        return

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(Engine, "after_cursor_execute", _after_cursor_execute)
    event.listen(Engine, "handle_error", _handle_error)

    _event = event
    _Engine = Engine
    _installed = True


def reset_sqlalchemy_instrumentation() -> None:
    global _should_trace_sqlalchemy, _get_storage, _event, _Engine, _installed

    if _installed and _event is not None and _Engine is not None:
        if _event.contains(_Engine, "before_cursor_execute", _before_cursor_execute):
            _event.remove(_Engine, "before_cursor_execute", _before_cursor_execute)
        if _event.contains(_Engine, "after_cursor_execute", _after_cursor_execute):
            _event.remove(_Engine, "after_cursor_execute", _after_cursor_execute)
        if _event.contains(_Engine, "handle_error", _handle_error):
            _event.remove(_Engine, "handle_error", _handle_error)

    _should_trace_sqlalchemy = lambda: False
    _get_storage = lambda: None
    _event = None
    _Engine = None
    _installed = False
