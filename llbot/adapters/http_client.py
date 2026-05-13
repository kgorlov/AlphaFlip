"""Small async JSON HTTP client wrapper."""

import asyncio
from collections.abc import Mapping
from typing import Any, Protocol

import aiohttp


class JsonHttpClient(Protocol):
    async def get_json(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any: ...

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any: ...


class HttpRequestError(RuntimeError):
    pass


class AioHttpJsonClient:
    def __init__(self, base_url: str, timeout_sec: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout_sec)

    async def get_json(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, params=params) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise HttpRequestError(f"GET {url} failed: {response.status} {body[:300]}")
                    return await response.json()
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise HttpRequestError(f"GET {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpRequestError(f"GET {url} failed: {exc}") from exc

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=dict(payload or {})) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise HttpRequestError(f"POST {url} failed: {response.status} {body[:300]}")
                    return await response.json()
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise HttpRequestError(f"POST {url} timed out") from exc
        except aiohttp.ClientError as exc:
            raise HttpRequestError(f"POST {url} failed: {exc}") from exc
