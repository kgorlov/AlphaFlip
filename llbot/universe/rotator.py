"""Live universe rotation."""

from collections.abc import Iterable

from llbot.universe.scorer import ScoredCandidate


def select_live_symbols(scored: Iterable[ScoredCandidate], top_n: int) -> list[str]:
    if top_n <= 0:
        return []
    ordered = sorted(scored, key=lambda item: item.score, reverse=True)
    return [item.symbol for item in ordered[:top_n]]

