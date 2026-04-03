from __future__ import annotations

import re
from dataclasses import dataclass

_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-(?P<parent_id>[0-9a-f]{16})-(?P<trace_flags>[0-9a-f]{2})$"
)
_ZERO_TRACE_ID = "0" * 32
_ZERO_PARENT_ID = "0" * 16


@dataclass(frozen=True)
class TraceParent:
    version: str
    trace_id: str
    parent_id: str
    trace_flags: str


def parse_traceparent(value: str | None) -> TraceParent | None:
    if not value:
        return None

    match = _TRACEPARENT_RE.fullmatch(value)
    if match is None:
        return None

    traceparent = TraceParent(**match.groupdict())
    if traceparent.version != "00":
        return None
    if traceparent.trace_id == _ZERO_TRACE_ID:
        return None
    if traceparent.parent_id == _ZERO_PARENT_ID:
        return None
    return traceparent
