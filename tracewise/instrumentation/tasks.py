from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.models import Span


async def context_task(
    coro: Coroutine,
    *,
    span: Span | None = None,
) -> asyncio.Task:
    """
    Schedule a coroutine as an asyncio Task with explicit trace context propagation.

    Use instead of asyncio.create_task() when you need to guarantee the current
    trace span is available inside the background task.

    Args:
        coro: The coroutine to run as a background task.
        span: Override the span to propagate. Defaults to get_current_span().

    Returns:
        The created asyncio.Task. Await it if you need the result.
    """
    active_span = span if span is not None else get_current_span()

    async def _wrapped():
        if active_span is not None:
            token = set_current_span(active_span)
            try:
                return await coro
            finally:
                reset_span(token)
        else:
            return await coro

    return asyncio.create_task(_wrapped())
