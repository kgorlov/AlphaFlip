"""Universe hydration entrypoint."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.config import load_config
from llbot.adapters.binance_spot import BinanceSpotRestClient
from llbot.adapters.binance_usdm import BinanceUsdmRestClient
from llbot.adapters.http_client import HttpRequestError
from llbot.adapters.http_client import AioHttpJsonClient
from llbot.adapters.mexc_contract import MexcContractRestClient
from llbot.adapters.mexc_spot import MexcSpotRestClient
from llbot.domain.models import SymbolProfile
from llbot.universe.provider import HybridUniverseProvider


async def _run(
    config_path: Path,
    limit: int | None,
    out: str | None = None,
    http_timeout_sec: float = 20.0,
) -> None:
    config = load_config(config_path)
    provider = HybridUniverseProvider(
        config.universe,
        binance_spot=BinanceSpotRestClient(AioHttpJsonClient("https://api.binance.com", http_timeout_sec)),
        binance_usdm=BinanceUsdmRestClient(AioHttpJsonClient("https://fapi.binance.com", http_timeout_sec)),
        mexc_spot=MexcSpotRestClient(AioHttpJsonClient("https://api.mexc.com", http_timeout_sec)),
        mexc_contract=MexcContractRestClient(AioHttpJsonClient("https://contract.mexc.com", http_timeout_sec)),
        depth_hydration_limit=limit,
    )
    try:
        profiles = await provider.refresh()
    except HttpRequestError as exc:
        print(f"Universe hydration failed: {exc}")
        return
    payload = profiles_payload(profiles)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
    for idx, profile in enumerate(profiles, start=1):
        score = profile.metadata.get("universe_score", "n/a")
        spread = profile.metadata.get("spread_bps_mexc", "n/a")
        depth = profile.metadata.get("top5_depth_usd_mexc", "n/a")
        print(
            f"{idx:03d} {profile.canonical_symbol} -> {profile.lagger_symbol} "
            f"score={score} mexc_spread_bps={spread} mexc_depth_usd={depth}"
        )


def profiles_payload(profiles: list[SymbolProfile]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "safety": {
            "orders_submitted": False,
            "orders_cancelled": False,
            "secrets_read": False,
            "live_trading_enabled": False,
        },
        "candidates": [_profile_payload(idx, profile) for idx, profile in enumerate(profiles, start=1)],
    }


def _profile_payload(rank: int, profile: SymbolProfile) -> dict[str, Any]:
    return {
        "rank": rank,
        "canonical_symbol": profile.canonical_symbol,
        "leader_symbol": profile.leader_symbol,
        "lagger_symbol": profile.lagger_symbol,
        "profile": profile.profile.value,
        "leader_market": profile.leader_market.value,
        "lagger_market": profile.lagger_market.value,
        "min_qty": _text(profile.min_qty),
        "qty_step": _text(profile.qty_step),
        "price_tick": _text(profile.price_tick),
        "min_notional_usd": _text(profile.min_notional_usd),
        "contract_size": _text(profile.contract_size),
        "maker_fee_bps": _text(profile.maker_fee_bps),
        "taker_fee_bps": _text(profile.taker_fee_bps),
        "metadata": {str(key): _text(value) for key, value in profile.metadata.items()},
    }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hydrate and rank the Binance/MEXC universe.")
    parser.add_argument("--config", default="conf/config.example.yaml")
    parser.add_argument(
        "--depth-limit",
        type=int,
        default=None,
        help="Number of coarse candidates to hydrate with depth snapshots.",
    )
    parser.add_argument("--out", help="Write ranked universe candidates to JSON.")
    parser.add_argument("--http-timeout-sec", type=float, default=20.0)
    args = parser.parse_args()
    asyncio.run(_run(Path(args.config), args.depth_limit, args.out, args.http_timeout_sec))


if __name__ == "__main__":
    main()
