import asyncio
from datetime import datetime, timezone

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus


def utcnow():
    return datetime.now(timezone.utc)


def _span(trace_id: str, span_id: str) -> Span:
    return Span(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=None,
        name="test",
        kind=SpanKind.SERVER,
        start_time=utcnow(),
        end_time=None,
        status=SpanStatus.UNSET,
    )


def test_default_is_none():
    assert get_current_span() is None


def test_set_and_get():
    span = _span("t1", "s1")
    token = set_current_span(span)
    assert get_current_span() is span
    reset_span(token)


def test_reset_restores_previous():
    span = _span("t1", "s1")
    token = set_current_span(span)
    assert get_current_span() is span
    reset_span(token)
    assert get_current_span() is None


async def test_context_isolation_across_tasks():
    """Two concurrent tasks must not see each other's spans."""
    span1 = _span("trace-1", "span-1")
    span2 = _span("trace-2", "span-2")
    results = {}

    async def task_a():
        token = set_current_span(span1)
        await asyncio.sleep(0.01)
        results["a"] = get_current_span()
        reset_span(token)

    async def task_b():
        token = set_current_span(span2)
        await asyncio.sleep(0.01)
        results["b"] = get_current_span()
        reset_span(token)

    await asyncio.gather(task_a(), task_b())
    assert results["a"] is span1
    assert results["b"] is span2
