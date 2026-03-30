from __future__ import annotations

from abc import ABC, abstractmethod

from tracewise.core.models import Span


class BaseStorage(ABC):
    @abstractmethod
    def save_span(self, span: Span) -> None: ...

    @abstractmethod
    def update_span(self, span: Span) -> None: ...

    @abstractmethod
    def get_trace(self, trace_id: str) -> list[Span]: ...

    @abstractmethod
    def list_traces(self, limit: int = 50) -> list[str]: ...

    @abstractmethod
    def delete_old_traces(self, keep: int) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...
