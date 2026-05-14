"""Live universe rotation."""

from dataclasses import dataclass
from collections.abc import Iterable

from llbot.adapters.binance_ws import book_ticker_stream_name
from llbot.adapters.mexc_contract_ws import subscribe_ticker, unsubscribe_ticker
from llbot.adapters.mexc_spot_ws import (
    subscribe_book_ticker as subscribe_spot_book_ticker,
    unsubscribe_book_ticker as unsubscribe_spot_book_ticker,
)
from llbot.domain.enums import MarketProfileName
from llbot.domain.models import SymbolProfile
from llbot.universe.scorer import ScoredCandidate
from llbot.universe.symbol_mapper import normalize_mexc_contract_symbol, normalize_mexc_spot_symbol


@dataclass(frozen=True, slots=True)
class LiveUniverseSelection:
    profiles: tuple[SymbolProfile, ...]
    canonical_symbols: tuple[str, ...]
    binance_streams: tuple[str, ...]
    mexc_subscriptions: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class UniverseRotationPlan:
    selected: LiveUniverseSelection
    keep_symbols: tuple[str, ...]
    subscribe_symbols: tuple[str, ...]
    unsubscribe_symbols: tuple[str, ...]
    binance_subscribe_streams: tuple[str, ...]
    binance_unsubscribe_streams: tuple[str, ...]
    mexc_subscriptions: tuple[dict[str, object], ...]
    mexc_unsubscriptions: tuple[dict[str, object], ...]


def select_live_symbols(scored: Iterable[ScoredCandidate], top_n: int) -> list[str]:
    if top_n <= 0:
        return []
    ordered = sorted(scored, key=lambda item: item.score, reverse=True)
    return [item.symbol for item in ordered[:top_n]]


def select_live_profiles(
    profiles: Iterable[SymbolProfile],
    top_n: int,
    max_active_symbols: int | None = None,
) -> LiveUniverseSelection:
    if top_n <= 0:
        return LiveUniverseSelection((), (), (), ())
    limit = top_n if max_active_symbols is None else min(top_n, max_active_symbols)
    if limit <= 0:
        return LiveUniverseSelection((), (), (), ())
    ordered = sorted(profiles, key=_profile_sort_key)
    selected = tuple(ordered[:limit])
    return LiveUniverseSelection(
        profiles=selected,
        canonical_symbols=tuple(profile.canonical_symbol for profile in selected),
        binance_streams=tuple(book_ticker_stream_name(profile.leader_symbol) for profile in selected),
        mexc_subscriptions=tuple(_mexc_subscribe_message(profile) for profile in selected),
    )


def plan_live_universe_rotation(
    current_symbols: Iterable[str],
    ranked_profiles: Iterable[SymbolProfile],
    top_n: int,
    max_active_symbols: int | None = None,
) -> UniverseRotationPlan:
    selected = select_live_profiles(ranked_profiles, top_n, max_active_symbols)
    current = tuple(dict.fromkeys(current_symbols))
    next_symbols = selected.canonical_symbols
    current_set = set(current)
    next_set = set(next_symbols)
    profile = selected.profiles[0].profile if selected.profiles else MarketProfileName.PERP_TO_PERP
    keep = tuple(symbol for symbol in current if symbol in next_set)
    subscribe = tuple(symbol for symbol in next_symbols if symbol not in current_set)
    unsubscribe = tuple(symbol for symbol in current if symbol not in next_set)
    profiles_by_symbol = {profile.canonical_symbol: profile for profile in selected.profiles}
    return UniverseRotationPlan(
        selected=selected,
        keep_symbols=keep,
        subscribe_symbols=subscribe,
        unsubscribe_symbols=unsubscribe,
        binance_subscribe_streams=tuple(
            book_ticker_stream_name(profiles_by_symbol[symbol].leader_symbol) for symbol in subscribe
        ),
        binance_unsubscribe_streams=tuple(
            book_ticker_stream_name(symbol) for symbol in unsubscribe
        ),
        mexc_subscriptions=tuple(
            _mexc_subscribe_message(profiles_by_symbol[symbol]) for symbol in subscribe
        ),
        mexc_unsubscriptions=tuple(_mexc_unsubscribe_message(symbol, profile) for symbol in unsubscribe),
    )


def _profile_sort_key(profile: SymbolProfile) -> tuple[float, str]:
    score = profile.metadata.get("universe_score", "0")
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = 0.0
    return (-score_value, profile.canonical_symbol)


def _mexc_subscribe_message(profile: SymbolProfile) -> dict[str, object]:
    if profile.profile == MarketProfileName.PERP_TO_PERP:
        return subscribe_ticker(profile.lagger_symbol).message
    return subscribe_spot_book_ticker(profile.lagger_symbol).message


def _mexc_unsubscribe_message(symbol: str, profile: MarketProfileName) -> dict[str, object]:
    if profile == MarketProfileName.PERP_TO_PERP:
        return unsubscribe_ticker(normalize_mexc_contract_symbol(symbol)).message
    return unsubscribe_spot_book_ticker(normalize_mexc_spot_symbol(symbol)).message
