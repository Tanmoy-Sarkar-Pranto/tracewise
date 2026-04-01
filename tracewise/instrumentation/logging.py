from __future__ import annotations

import logging
from datetime import datetime, timezone

from tracewise.core.context import get_current_span
from tracewise.core.models import SpanEvent


class TraceWiseLogHandler(logging.Handler):
    """
    A logging.Handler that attaches log records to the active TraceWise span
    as SpanEvents. No-op when no span is active.

    Usage:
        logging.getLogger().addHandler(TraceWiseLogHandler())
        # or via tracewise.init(app, capture_logs=True)
    """

    def emit(self, record: logging.LogRecord) -> None:
        span = get_current_span()
        if span is None:
            return
        span.events.append(SpanEvent(
            name=f"log.{record.levelname}",
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc),
            attributes={
                "log.message": record.getMessage(),
                "log.level": record.levelname,
                "log.logger": record.name,
            },
        ))
