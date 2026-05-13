"""Hybrid Binance/MEXC universe provider."""

import asyncio
from dataclasses import replace
from decimal import Decimal

from llbot.adapters.binance_spot import BinanceSpotRestClient
from llbot.adapters.binance_usdm import BinanceUsdmRestClient
from llbot.adapters.http_client import HttpRequestError
from llbot.adapters.mexc_contract import MexcContractRestClient
from llbot.adapters.mexc_spot import MexcSpotRestClient
from llbot.config import UniverseConfig
from llbot.domain.enums import MarketProfileName
from llbot.domain.market_data import BookTicker, ExchangeSymbolInfo, OrderBookDepth, Stats24h
from llbot.domain.models import SymbolProfile
from llbot.universe.filters import UniverseCandidate, UniverseFilterConfig, evaluate_candidate
from llbot.universe.scorer import ScoredCandidate, rank_candidates
from llbot.universe.symbol_mapper import SymbolMapper


class HybridUniverseProvider:
    """Builds a tradable symbol universe from direct exchange metadata and snapshots."""

    def __init__(
        self,
        config: UniverseConfig,
        binance_spot: BinanceSpotRestClient | None = None,
        binance_usdm: BinanceUsdmRestClient | None = None,
        mexc_spot: MexcSpotRestClient | None = None,
        mexc_contract: MexcContractRestClient | None = None,
        depth_hydration_limit: int | None = None,
        depth_levels: int = 5,
        depth_spacing_sec: float = 0.12,
    ) -> None:
        self.config = config
        self.binance_spot = binance_spot or BinanceSpotRestClient()
        self.binance_usdm = binance_usdm or BinanceUsdmRestClient()
        self.mexc_spot = mexc_spot or MexcSpotRestClient()
        self.mexc_contract = mexc_contract or MexcContractRestClient()
        self.depth_hydration_limit = depth_hydration_limit or max(1, min(config.top_n_live, 10))
        self.depth_levels = depth_levels
        self.depth_spacing_sec = depth_spacing_sec

    async def refresh(self) -> list[SymbolProfile]:
        if self.config.active_profile == MarketProfileName.SPOT_TO_SPOT:
            return await self._refresh_spot_to_spot()
        if self.config.active_profile == MarketProfileName.PERP_TO_PERP:
            return await self._refresh_perp_to_perp()
        raise ValueError(f"Unsupported profile: {self.config.active_profile}")

    async def _refresh_spot_to_spot(self) -> list[SymbolProfile]:
        leader_info, leader_stats, leader_books, lagger_info, lagger_stats, lagger_books = (
            await asyncio.gather(
                self.binance_spot.exchange_info(),
                self.binance_spot.ticker_24hr(),
                self.binance_spot.book_ticker(),
                self.mexc_spot.exchange_info(),
                self.mexc_spot.ticker_24hr(),
                self.mexc_spot.book_ticker(),
            )
        )
        mapper = SymbolMapper(MarketProfileName.SPOT_TO_SPOT)
        return await self._build_profiles(
            mapper=mapper,
            leader_info=_by_symbol(leader_info),
            leader_stats=leader_stats,
            leader_books=leader_books,
            lagger_info=_by_symbol(lagger_info),
            lagger_stats=lagger_stats,
            lagger_books=lagger_books,
            leader_depth=self.binance_spot.depth,
            lagger_depth=self.mexc_spot.depth,
        )

    async def _refresh_perp_to_perp(self) -> list[SymbolProfile]:
        leader_info, leader_stats, leader_books, lagger_info, lagger_ticker = await asyncio.gather(
            self.binance_usdm.exchange_info(),
            self.binance_usdm.ticker_24hr(),
            self.binance_usdm.book_ticker(),
            self.mexc_contract.contract_detail(),
            self.mexc_contract.ticker(),
        )
        lagger_stats, lagger_books = lagger_ticker
        mapper = SymbolMapper(MarketProfileName.PERP_TO_PERP)
        lagger_by_leader = {mapper.to_leader(item.symbol): item for item in lagger_info}
        lagger_stats_by_leader = {mapper.to_leader(k): v for k, v in lagger_stats.items()}
        lagger_books_by_leader = {mapper.to_leader(k): v for k, v in lagger_books.items()}
        return await self._build_profiles(
            mapper=mapper,
            leader_info=_by_symbol(leader_info),
            leader_stats=leader_stats,
            leader_books=leader_books,
            lagger_info=lagger_by_leader,
            lagger_stats=lagger_stats_by_leader,
            lagger_books=lagger_books_by_leader,
            leader_depth=self.binance_usdm.depth,
            lagger_depth=self.mexc_contract.depth,
        )

    async def _build_profiles(
        self,
        mapper: SymbolMapper,
        leader_info: dict[str, ExchangeSymbolInfo],
        leader_stats: dict[str, Stats24h],
        leader_books: dict[str, BookTicker],
        lagger_info: dict[str, ExchangeSymbolInfo],
        lagger_stats: dict[str, Stats24h],
        lagger_books: dict[str, BookTicker],
        leader_depth,
        lagger_depth,
    ) -> list[SymbolProfile]:
        shared = sorted(
            set(leader_info)
            & set(leader_stats)
            & set(leader_books)
            & set(lagger_info)
            & set(lagger_stats)
            & set(lagger_books)
        )
        coarse = sorted(
            shared,
            key=lambda symbol: min(
                leader_stats[symbol].quote_volume,
                lagger_stats[symbol].quote_volume,
            ),
            reverse=True,
        )

        candidates: list[UniverseCandidate] = []
        depths_by_symbol: dict[str, tuple[OrderBookDepth, OrderBookDepth]] = {}
        for symbol in coarse[: self.depth_hydration_limit]:
            await asyncio.sleep(self.depth_spacing_sec)
            try:
                l_depth, m_depth = await asyncio.gather(
                    leader_depth(symbol, self.depth_levels),
                    lagger_depth(mapper.to_lagger(symbol), self.depth_levels),
                )
            except HttpRequestError:
                continue
            depths_by_symbol[symbol] = (l_depth, m_depth)
            candidates.append(
                _candidate_from_snapshots(
                    symbol=symbol,
                    leader_info=leader_info[symbol],
                    lagger_info=lagger_info[symbol],
                    leader_stats=leader_stats[symbol],
                    lagger_stats=lagger_stats[symbol],
                    leader_book=leader_books[symbol],
                    lagger_book=lagger_books[symbol],
                    leader_depth=l_depth,
                    lagger_depth=m_depth,
                )
            )

        filter_config = UniverseFilterConfig(
            min_quote_volume_usd_24h=self.config.min_quote_volume_usd_24h,
            max_spread_bps=self.config.max_spread_bps,
            min_top5_depth_usd=self.config.min_top5_depth_usd,
            max_tick_bps=self.config.max_tick_bps,
        )
        allowed: list[UniverseCandidate] = []
        decisions: dict[str, str] = {}
        for candidate in candidates:
            decision = evaluate_candidate(candidate, filter_config)
            decisions[candidate.symbol] = decision.reason
            if decision.allowed:
                allowed.append(candidate)

        ranked = rank_candidates(allowed)
        return [
            _profile_from_scored(mapper, scored, lagger_info[scored.symbol], decisions[scored.symbol])
            for scored in ranked[: self.config.top_n_live]
            if scored.symbol in depths_by_symbol
        ]


def _candidate_from_snapshots(
    symbol: str,
    leader_info: ExchangeSymbolInfo,
    lagger_info: ExchangeSymbolInfo,
    leader_stats: Stats24h,
    lagger_stats: Stats24h,
    leader_book: BookTicker,
    lagger_book: BookTicker,
    leader_depth: OrderBookDepth,
    lagger_depth: OrderBookDepth,
) -> UniverseCandidate:
    mid = lagger_book.mid if lagger_book.mid > 0 else Decimal("1")
    tick = lagger_info.price_tick or Decimal("0")
    contract_size = lagger_info.contract_size
    return UniverseCandidate(
        symbol=symbol,
        leader_trading_enabled=leader_info.trading_enabled,
        lagger_trading_enabled=lagger_info.trading_enabled,
        lagger_api_allowed=lagger_info.api_allowed,
        quote_volume_binance_24h=leader_stats.quote_volume,
        quote_volume_mexc_24h=lagger_stats.quote_volume,
        top5_depth_usd_binance=leader_depth.top_depth_usd(5),
        top5_depth_usd_mexc=lagger_depth.top_depth_usd(5, contract_size),
        spread_bps_binance=leader_book.spread_bps,
        spread_bps_mexc=lagger_book.spread_bps,
        tick_size_bps_mexc=Decimal("10000") * tick / mid,
        fee_budget_bps=_fee_budget_bps(lagger_info),
        volatility_noise_bps=Decimal("0"),
    )


def _profile_from_scored(
    mapper: SymbolMapper,
    scored: ScoredCandidate,
    lagger_info: ExchangeSymbolInfo,
    filter_reason: str,
) -> SymbolProfile:
    candidate = scored.candidate
    base = mapper.build_profile(scored.symbol)
    return replace(
        base,
        min_qty=lagger_info.min_qty,
        qty_step=lagger_info.qty_step,
        price_tick=lagger_info.price_tick,
        min_notional_usd=lagger_info.min_notional,
        contract_size=lagger_info.contract_size,
        maker_fee_bps=_rate_to_bps(lagger_info.maker_fee_rate),
        taker_fee_bps=_rate_to_bps(lagger_info.taker_fee_rate),
        metadata={
            "universe_score": str(scored.score),
            "filter_reason": filter_reason,
            "quote_volume_binance_24h": str(candidate.quote_volume_binance_24h),
            "quote_volume_mexc_24h": str(candidate.quote_volume_mexc_24h),
            "top5_depth_usd_binance": str(candidate.top5_depth_usd_binance),
            "top5_depth_usd_mexc": str(candidate.top5_depth_usd_mexc),
            "spread_bps_binance": str(candidate.spread_bps_binance),
            "spread_bps_mexc": str(candidate.spread_bps_mexc),
            "tick_size_bps_mexc": str(candidate.tick_size_bps_mexc),
            "fee_budget_bps": str(candidate.fee_budget_bps),
        },
    )


def _fee_budget_bps(info: ExchangeSymbolInfo) -> Decimal:
    maker = _rate_to_bps(info.maker_fee_rate) or Decimal("0")
    taker = _rate_to_bps(info.taker_fee_rate) or Decimal("6")
    return maker + taker


def _rate_to_bps(rate: Decimal | None) -> Decimal | None:
    if rate is None:
        return None
    return Decimal("10000") * rate


def _by_symbol(items: list[ExchangeSymbolInfo]) -> dict[str, ExchangeSymbolInfo]:
    return {item.symbol: item for item in items}

