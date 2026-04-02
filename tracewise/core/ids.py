from __future__ import annotations

import secrets
from uuid import uuid4


def generate_trace_id() -> str:
    return uuid4().hex


def generate_span_id() -> str:
    span_id = secrets.token_hex(8)
    while span_id == "0000000000000000":
        span_id = secrets.token_hex(8)
    return span_id
