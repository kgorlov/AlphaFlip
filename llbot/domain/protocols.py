"""Interfaces that implementation modules must satisfy."""

from typing import Protocol

from llbot.domain.models import ExecutionAck, Intent, PortfolioState, Quote, SymbolProfile, Trade


class UniverseProvider(Protocol):
    async def refresh(self) -> list[SymbolProfile]: ...


class SignalModel(Protocol):
    def on_quote(self, q: Quote) -> list[Intent]: ...

    def on_trade(self, t: Trade) -> list[Intent]: ...


class Executor(Protocol):
    async def submit(self, intent: Intent) -> ExecutionAck: ...

    async def cancel(self, order_id: str) -> None: ...


class RiskEngine(Protocol):
    def allow(self, intent: Intent, state: PortfolioState) -> tuple[bool, str]: ...

