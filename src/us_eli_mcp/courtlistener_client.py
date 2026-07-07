"""Async httpx client for the CourtListener search API (Free Law Project).

The ``/api/rest/v4/search/`` endpoint is anonymous/keyless (live-verified
2026-07-07; rate-limited to roughly 5 requests/min for anonymous callers).
The single-item ``/opinions/{id}/``, ``/clusters/{id}/`` and ``/dockets/{id}/``
endpoints require authentication and are NOT used here - a single case is
fetched through the same search endpoint with a ``cluster_id:{id}`` field
query instead.

Scope note (anti-duplication, decided 2026-07-06 and 2026-07-07): FEDERAL
enacted-law text in this connector comes from GovInfo, and federal case law
overlaps with other mature CourtListener MCP wrappers. The headline value of
this client is STATE case law - CourtListener is the only keyless source with
millions of state-court opinions (GovInfo has none). The endpoint covers both;
use the ``court`` filter (e.g. ``cal``, ``ny``, ``texapp``) to scope.

Live-verified totals (2026-07-07): 8 294 123 opinions in the unfiltered
``/search/?type=o`` ``count`` field.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_COURTLISTENER_BASE_URL = "https://www.courtlistener.com/api/rest/v4"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "us-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/us-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class CourtListenerClient:
    """Async client. Use as ``async with CourtListenerClient() as c: ...`` (keyless)."""

    def __init__(
        self,
        base_url: str = DEFAULT_COURTLISTENER_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> CourtListenerClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(self, path: str, params: dict[str, str], *, category: str) -> dict:
        url = f"{self.base_url}{path}"
        cache_key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=params)
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

    async def search_opinions(
        self, query: str, court: str | None = None, limit: int = 20
    ) -> tuple[int, list[dict]]:
        """Full-text search over case-law opinions (state + federal).

        Returns ``(total_count, results)`` - ``total_count`` is the API's own
        ``count`` field, not ``len(results)``.
        """
        params = {"q": query, "type": "o"}
        if court:
            params["court"] = court
        data = await self._get_json("/search/", params, category="search")
        return int(data.get("count", 0)), data.get("results", [])[:limit]

    async def get_opinion_cluster(self, cluster_id: int) -> dict | None:
        """Fetch one opinion cluster by id via a ``cluster_id:{id}`` field query
        (the keyless path - the ``/clusters/{id}/`` endpoint requires auth).
        """
        params = {"q": f"cluster_id:{cluster_id}", "type": "o"}
        data = await self._get_json("/search/", params, category="act")
        results = data.get("results", [])
        return results[0] if results else None
