from __future__ import annotations

from contextvars import ContextVar, Token

from tracewise.core.models import Span

_current_span: ContextVar[Span | None] = ContextVar("tracewise_current_span", default=None)


def get_current_span() -> Span | None:
    return _current_span.get()


def set_current_span(span: Span) -> Token:
    return _current_span.set(span)


def reset_span(token: Token) -> None:
    _current_span.reset(token)
