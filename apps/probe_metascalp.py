"""Probe local MetaScalp instance and list visible connections."""

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llbot.adapters.http_client import AioHttpJsonClient
from llbot.adapters.metascalp import MetaScalpClient, discover_metascalp


async def _run(host: str, port_min: int, port_max: int) -> None:
    instance = await discover_metascalp(host=host, port_min=port_min, port_max=port_max)
    if instance is None:
        print(f"MetaScalp not found on {host}:{port_min}-{port_max}")
        return

    print(f"MetaScalp found at {instance.base_url}: {instance.ping}")
    client = MetaScalpClient(AioHttpJsonClient(instance.base_url))
    for connection in await client.connections():
        print(
            f"id={connection.id} exchange={connection.exchange} market={connection.market} "
            f"state={connection.state} demo={connection.demo_mode} view={connection.view_mode}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover local MetaScalp and list connections.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port-min", type=int, default=17845)
    parser.add_argument("--port-max", type=int, default=17855)
    args = parser.parse_args()
    asyncio.run(_run(args.host, args.port_min, args.port_max))


if __name__ == "__main__":
    main()
