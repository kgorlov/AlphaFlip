"""Event envelope types for the event-driven pipeline."""

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Event(Generic[T]):
    event_type: str
    payload: T
    local_ts_ms: int

