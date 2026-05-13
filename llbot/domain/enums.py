"""Shared enums."""

from enum import Enum


class Venue(str, Enum):
    BINANCE = "binance"
    MEXC = "mexc"
    METASCALP = "metascalp"


class MarketType(str, Enum):
    SPOT = "spot"
    USDT_PERP = "usdt_perp"


class MarketProfileName(str, Enum):
    SPOT_TO_SPOT = "spot_to_spot"
    PERP_TO_PERP = "perp_to_perp"


class RuntimeMode(str, Enum):
    SHADOW = "shadow"
    PAPER = "paper"
    METASCALP_DEMO = "metascalp-demo"
    LIVE = "live"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class IntentType(str, Enum):
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"


class OrderStyle(str, Enum):
    AGGRESSIVE_LIMIT = "aggressive_limit"
    PASSIVE_LIMIT = "passive_limit"
