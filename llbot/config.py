"""Configuration loading and validation helpers."""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from llbot.domain.enums import MarketProfileName, RuntimeMode


@dataclass(frozen=True, slots=True)
class UniverseConfig:
    active_profile: MarketProfileName = MarketProfileName.PERP_TO_PERP
    refresh_sec: int = 30
    top_n_live: int = 40
    min_quote_volume_usd_24h: Decimal = Decimal("2000000")
    max_spread_bps: Decimal = Decimal("12")
    min_top5_depth_usd: Decimal = Decimal("25000")
    max_tick_bps: Decimal = Decimal("4")


@dataclass(frozen=True, slots=True)
class SignalConfig:
    model: str = "residual_zscore_plus_impulse"
    z_entry: Decimal = Decimal("2.2")
    z_exit: Decimal = Decimal("0.4")
    impulse_windows_ms: tuple[int, ...] = (50, 100, 200, 500)
    lag_candidates_ms: tuple[int, ...] = (25, 50, 100, 200, 500, 1000)
    safety_bps: Decimal = Decimal("2.0")


@dataclass(frozen=True, slots=True)
class MetaScalpConfig:
    host: str = "127.0.0.1"
    port_min: int = 17845
    port_max: int = 17855
    require_demo_mode: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    venue: str = "metascalp"
    style: str = "auto"
    taker_min_edge_bps: Decimal = Decimal("8")
    maker_min_edge_bps: Decimal = Decimal("14")
    ttl_ms: int = 3000
    reduce_only_on_exit: bool = True
    metascalp: MetaScalpConfig = field(default_factory=MetaScalpConfig)


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_open_positions: int = 5
    max_active_symbols: int = 5
    max_notional_per_symbol_usd: Decimal = Decimal("500")
    max_total_notional_usd: Decimal = Decimal("1500")
    max_daily_loss_usd: Decimal = Decimal("150")
    stale_feed_ms: int = 1500
    desync_book_resets_before_block: int = 3
    max_repeated_order_errors: int = 3
    max_slippage_bps: Decimal = Decimal("10")


@dataclass(frozen=True, slots=True)
class StorageConfig:
    duckdb_path: Path = Path("data/leadlag.duckdb")
    parquet_root: Path = Path("data/parquet")


@dataclass(frozen=True, slots=True)
class AppConfig:
    runtime_mode: RuntimeMode = RuntimeMode.SHADOW
    live_requires_runtime_confirmation: bool = True
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


def load_config(path: str | Path) -> AppConfig:
    """Load YAML config into typed dataclasses."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on local env setup
        raise RuntimeError("PyYAML is required to load config files") from exc

    with Path(path).open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    runtime = _mapping(raw.get("runtime"))
    universe = _mapping(raw.get("universe"))
    signal = _mapping(raw.get("signal"))
    execution = _mapping(raw.get("execution"))
    metascalp = _mapping(execution.get("metascalp"))
    risk = _mapping(raw.get("risk"))
    storage = _mapping(raw.get("storage"))

    runtime_mode = RuntimeMode(runtime.get("mode", RuntimeMode.SHADOW.value))
    if runtime_mode == RuntimeMode.LIVE and runtime.get("live_requires_runtime_confirmation", True):
        raise ValueError("Live mode cannot be loaded without explicit runtime confirmation flow")

    return AppConfig(
        runtime_mode=runtime_mode,
        live_requires_runtime_confirmation=bool(
            runtime.get("live_requires_runtime_confirmation", True)
        ),
        universe=UniverseConfig(
            active_profile=MarketProfileName(
                universe.get("active_profile", MarketProfileName.PERP_TO_PERP.value)
            ),
            refresh_sec=int(universe.get("refresh_sec", 30)),
            top_n_live=int(universe.get("top_n_live", 40)),
            min_quote_volume_usd_24h=_decimal(
                universe.get("min_quote_volume_usd_24h", "2000000")
            ),
            max_spread_bps=_decimal(universe.get("max_spread_bps", "12")),
            min_top5_depth_usd=_decimal(universe.get("min_top5_depth_usd", "25000")),
            max_tick_bps=_decimal(universe.get("max_tick_bps", "4")),
        ),
        signal=SignalConfig(
            model=str(signal.get("model", "residual_zscore_plus_impulse")),
            z_entry=_decimal(signal.get("z_entry", "2.2")),
            z_exit=_decimal(signal.get("z_exit", "0.4")),
            impulse_windows_ms=tuple(int(x) for x in signal.get("impulse_windows_ms", []))
            or (50, 100, 200, 500),
            lag_candidates_ms=tuple(int(x) for x in signal.get("lag_candidates_ms", []))
            or (25, 50, 100, 200, 500, 1000),
            safety_bps=_decimal(signal.get("safety_bps", "2.0")),
        ),
        execution=ExecutionConfig(
            venue=str(execution.get("venue", "metascalp")),
            style=str(execution.get("style", "auto")),
            taker_min_edge_bps=_decimal(execution.get("taker_min_edge_bps", "8")),
            maker_min_edge_bps=_decimal(execution.get("maker_min_edge_bps", "14")),
            ttl_ms=int(execution.get("ttl_ms", 3000)),
            reduce_only_on_exit=bool(execution.get("reduce_only_on_exit", True)),
            metascalp=MetaScalpConfig(
                host=str(metascalp.get("host", "127.0.0.1")),
                port_min=int(metascalp.get("port_min", 17845)),
                port_max=int(metascalp.get("port_max", 17855)),
                require_demo_mode=bool(metascalp.get("require_demo_mode", True)),
            ),
        ),
        risk=RiskConfig(
            max_open_positions=int(risk.get("max_open_positions", 5)),
            max_active_symbols=int(risk.get("max_active_symbols", 5)),
            max_notional_per_symbol_usd=_decimal(
                risk.get("max_notional_per_symbol_usd", "500")
            ),
            max_total_notional_usd=_decimal(risk.get("max_total_notional_usd", "1500")),
            max_daily_loss_usd=_decimal(risk.get("max_daily_loss_usd", "150")),
            stale_feed_ms=int(risk.get("stale_feed_ms", 1500)),
            desync_book_resets_before_block=int(
                risk.get("desync_book_resets_before_block", 3)
            ),
            max_repeated_order_errors=int(risk.get("max_repeated_order_errors", 3)),
            max_slippage_bps=_decimal(risk.get("max_slippage_bps", "10")),
        ),
        storage=StorageConfig(
            duckdb_path=Path(str(storage.get("duckdb_path", "data/leadlag.duckdb"))),
            parquet_root=Path(str(storage.get("parquet_root", "data/parquet"))),
        ),
    )


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Expected config section to be a mapping")
    return value


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))
