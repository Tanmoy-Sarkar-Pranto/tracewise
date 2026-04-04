from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tracewise.storage.base import BaseStorage

_should_trace_sqlalchemy: Callable[[], bool] = lambda: False
_get_storage: Callable[[], BaseStorage | None] = lambda: None
_event: Any = None
_Engine: Any = None
_installed = False


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    return None


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    return None


def _handle_error(exception_context):
    return None


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
