"""MetaScalp local REST discovery adapter."""

from dataclasses import dataclass, field
from typing import Any

from llbot.adapters.http_client import AioHttpJsonClient, HttpRequestError, JsonHttpClient


@dataclass(frozen=True, slots=True)
class MetaScalpInstance:
    host: str
    port: int
    ping: dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True, slots=True)
class MetaScalpConnection:
    id: int
    name: str
    exchange: str
    exchange_id: int | None
    market: str
    market_type: int | None
    state: int | None
    view_mode: bool
    demo_mode: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def connected(self) -> bool:
        return self.state == 2


class MetaScalpClient:
    def __init__(self, http: JsonHttpClient) -> None:
        self.http = http

    async def ping(self) -> dict[str, Any]:
        payload = await self.http.get_json("/ping")
        return payload if isinstance(payload, dict) else {"response": payload}

    async def connections(self) -> list[MetaScalpConnection]:
        payload = await self.http.get_json("/api/connections")
        items = payload if isinstance(payload, list) else _connection_items(payload)
        return [_parse_connection(item) for item in items if isinstance(item, dict)]

    async def place_order(self, connection_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.http.post_json(f"/api/connections/{connection_id}/orders", payload)
        return response if isinstance(response, dict) else {"response": response}

    async def cancel_order(self, connection_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.http.post_json(f"/api/connections/{connection_id}/orders/cancel", payload)
        return response if isinstance(response, dict) else {"response": response}

    async def select_connection(
        self,
        exchange: str = "mexc",
        market_contains: str | None = None,
        require_demo_mode: bool = True,
        require_connected: bool = True,
    ) -> MetaScalpConnection | None:
        exchange_l = exchange.lower()
        market_l = market_contains.lower() if market_contains else None
        for connection in await self.connections():
            if exchange_l not in connection.exchange.lower():
                continue
            if market_l and market_l not in connection.market.lower():
                continue
            if require_demo_mode and not connection.demo_mode:
                continue
            if require_connected and not connection.connected:
                continue
            return connection
        return None


async def discover_metascalp(
    host: str = "127.0.0.1",
    port_min: int = 17845,
    port_max: int = 17855,
    timeout_sec: float = 1.0,
) -> MetaScalpInstance | None:
    for port in range(port_min, port_max + 1):
        http = AioHttpJsonClient(f"http://{host}:{port}", timeout_sec=timeout_sec)
        client = MetaScalpClient(http)
        try:
            ping = await client.ping()
        except HttpRequestError:
            continue
        return MetaScalpInstance(host=host, port=port, ping=ping)
    return None


def _parse_connection(item: dict[str, Any]) -> MetaScalpConnection:
    return MetaScalpConnection(
        id=int(_get(item, "Id", "id")),
        name=str(_get(item, "Name", "name", default="")),
        exchange=str(_get(item, "Exchange", "exchange", default="")),
        exchange_id=_int_or_none(_get(item, "ExchangeId", "exchangeId", "exchange_id", default=None)),
        market=str(_get(item, "Market", "market", default="")),
        market_type=_int_or_none(_get(item, "MarketType", "marketType", "market_type", default=None)),
        state=_int_or_none(_get(item, "State", "state", default=None)),
        view_mode=bool(_get(item, "ViewMode", "viewMode", "view_mode", default=False)),
        demo_mode=bool(_get(item, "DemoMode", "demoMode", "demo_mode", default=False)),
        raw=item,
    )


def _connection_items(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    for key in ("Data", "data", "Connections", "connections"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _get(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return default


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
