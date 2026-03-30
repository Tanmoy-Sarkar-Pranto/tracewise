import asyncio
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.instrumentation.tasks import context_task


def utcnow():
    return datetime.now(timezone.utc)


def _span(trace_id: str) -> Span:
    return Span(
        trace_id=trace_id, span_id=uuid4().hex, parent_span_id=None,
        name="root", kind=SpanKind.SERVER,
        start_time=utcnow(), end_time=None, status=SpanStatus.UNSET,
    )


async def test_context_task_propagates_active_span():
    parent_span = _span("trace-bg-1")
    token = set_current_span(parent_span)
    seen = {}

    async def background():
        seen["span"] = get_current_span()

    task = await context_task(background())
    await task
    reset_span(token)

    assert seen["span"] is parent_span


async def test_context_task_with_explicit_span():
    explicit_span = _span("trace-bg-2")
    seen = {}

    async def background():
        seen["span"] = get_current_span()

    task = await context_task(background(), span=explicit_span)
    await task

    assert seen["span"] is explicit_span


async def test_context_task_no_span_propagates_none():
    assert get_current_span() is None
    seen = {"called": False}

    async def background():
        seen["called"] = True
        seen["span"] = get_current_span()

    task = await context_task(background())
    await task

    assert seen["called"] is True
    assert seen["span"] is None
