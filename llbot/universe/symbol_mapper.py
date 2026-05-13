"""Symbol mapping between Binance, MEXC, and canonical symbols."""

from dataclasses import dataclass

from llbot.domain.enums import MarketProfileName, MarketType, Venue
from llbot.domain.models import SymbolProfile


def binance_spot_to_mexc_spot(symbol: str) -> str:
    return normalize_binance_symbol(symbol)


def binance_usdm_to_mexc_contract(symbol: str) -> str:
    symbol = normalize_binance_symbol(symbol)
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}_USDT"
    return symbol


def mexc_contract_to_binance_usdm(symbol: str) -> str:
    return normalize_mexc_contract_symbol(symbol).replace("_", "")


def normalize_binance_symbol(symbol: str) -> str:
    return symbol.replace("-", "").replace("_", "").replace("/", "").upper()


def normalize_mexc_spot_symbol(symbol: str) -> str:
    return normalize_binance_symbol(symbol)


def normalize_mexc_contract_symbol(symbol: str) -> str:
    symbol = symbol.replace("-", "_").replace("/", "_").upper()
    if "_" in symbol:
        return symbol
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}_USDT"
    return symbol


@dataclass(frozen=True, slots=True)
class SymbolMapper:
    profile: MarketProfileName

    def to_lagger(self, leader_symbol: str) -> str:
        if self.profile == MarketProfileName.SPOT_TO_SPOT:
            return binance_spot_to_mexc_spot(leader_symbol)
        if self.profile == MarketProfileName.PERP_TO_PERP:
            return binance_usdm_to_mexc_contract(leader_symbol)
        raise ValueError(f"Unsupported market profile: {self.profile}")

    def to_leader(self, lagger_symbol: str) -> str:
        if self.profile == MarketProfileName.SPOT_TO_SPOT:
            return normalize_mexc_spot_symbol(lagger_symbol)
        if self.profile == MarketProfileName.PERP_TO_PERP:
            return mexc_contract_to_binance_usdm(lagger_symbol)
        raise ValueError(f"Unsupported market profile: {self.profile}")

    def build_profile(self, leader_symbol: str) -> SymbolProfile:
        leader = normalize_binance_symbol(leader_symbol)
        lagger = self.to_lagger(leader)
        if self.profile == MarketProfileName.SPOT_TO_SPOT:
            leader_market = MarketType.SPOT
            lagger_market = MarketType.SPOT
        elif self.profile == MarketProfileName.PERP_TO_PERP:
            leader_market = MarketType.USDT_PERP
            lagger_market = MarketType.USDT_PERP
        else:
            raise ValueError(f"Unsupported market profile: {self.profile}")

        return SymbolProfile(
            canonical_symbol=leader,
            leader_symbol=leader,
            lagger_symbol=lagger,
            profile=self.profile,
            leader_venue=Venue.BINANCE,
            lagger_venue=Venue.MEXC,
            leader_market=leader_market,
            lagger_market=lagger_market,
        )

