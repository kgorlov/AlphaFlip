"""Execution routing helpers."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionRoute:
    venue: str
    connection_id: str | None
    demo_mode: bool

