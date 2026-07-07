"""Async httpx client for the Congress.gov API (api.congress.gov).

Requires a free api.data.gov key (register in ~1 minute, no cost). Falls back
to the shared, low-rate-limit DEMO_KEY for quick local testing only - do not
run production traffic on DEMO_KEY.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://api.congress.gov/v3"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "us-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/us-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class CongressClient:
    """Async client. Use as ``async with CongressClient(api_key=...) as c: ...``."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> CongressClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(self, path: str, params: dict[str, str], *, category: str) -> dict:
        url = f"{self.base_url}{path}"
        req_params = {**params, "api_key": self._api_key, "format": "json"}
        cache_key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=req_params)
                resp.raise_for_status()
                data = resp.json()
                self._cache.set(cache_key, data, ttl=HttpCache.ttl_for(category))
                return data
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def list_bills(self, congress: int, bill_type: str, limit: int = 20) -> list[dict]:
        data = await self._get_json(
            f"/bill/{congress}/{bill_type}", {"limit": str(limit)}, category="search"
        )
        return data.get("bills", [])

    async def get_bill(self, congress: int, bill_type: str, number: int) -> dict:
        data = await self._get_json(f"/bill/{congress}/{bill_type}/{number}", {}, category="act")
        return data.get("bill", {})

