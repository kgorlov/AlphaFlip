"""Universe hydration entrypoint."""

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.config import load_config
from llbot.adapters.http_client import HttpRequestError
from llbot.universe.provider import HybridUniverseProvider


async def _run(config_path: Path, limit: int | None) -> None:
    config = load_config(config_path)
    provider = HybridUniverseProvider(config.universe, depth_hydration_limit=limit)
    try:
        profiles = await provider.refresh()
    except HttpRequestError as exc:
        print(f"Universe hydration failed: {exc}")
        return
    for idx, profile in enumerate(profiles, start=1):
        score = profile.metadata.get("universe_score", "n/a")
        spread = profile.metadata.get("spread_bps_mexc", "n/a")
        depth = profile.metadata.get("top5_depth_usd_mexc", "n/a")
        print(
            f"{idx:03d} {profile.canonical_symbol} -> {profile.lagger_symbol} "
            f"score={score} mexc_spread_bps={spread} mexc_depth_usd={depth}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Hydrate and rank the Binance/MEXC universe.")
    parser.add_argument("--config", default="conf/config.example.yaml")
    parser.add_argument(
        "--depth-limit",
        type=int,
        default=None,
        help="Number of coarse candidates to hydrate with depth snapshots.",
    )
    args = parser.parse_args()
    asyncio.run(_run(Path(args.config), args.depth_limit))


if __name__ == "__main__":
    main()
