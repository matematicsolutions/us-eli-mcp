"""Async httpx client for the GovInfo API (api.govinfo.gov).

GovInfo (US Government Publishing Office) is a separate API family from
Congress.gov, sharing only the api.data.gov key/DEMO_KEY convention. It
covers enacted law text (US Code, Statutes at Large) and the Federal
Register - the gap this connector's own DISCOVERY.md names as the natural
v0.2 feature, distinct from CourtListener case law (out of scope - see
DISCOVERY.md for why).

Endpoint shapes below were live-verified against api.govinfo.gov and cross-
checked against the official docs (github.com/usgpo/api):

- ``/collections`` - list every collection code (e.g. ``USCODE``, ``CFR``, ``FR``).
- ``/collections/{collection}/{startDate}`` - list packages in a collection
  modified since ``startDate`` (ISO 8601, e.g. ``2023-01-01T00:00:00Z``).
  Requires ``offsetMark`` (``*`` for the first page) and ``pageSize``.
- ``/packages/{packageId}/summary`` - metadata + content-format links for one package.
- ``/packages/{packageId}/granules`` - sub-documents of a package (e.g. one US
  Code title split into granules); also paginated via ``offsetMark``.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_GOVINFO_BASE_URL = "https://api.govinfo.gov"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "us-eli-mcp/0.2.0 (+https://github.com/matematicsolutions/us-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# DEMO_KEY caveat (SOURCES.md / DISCOVERY.md): shared, low, easily exhausted by
# other users of the public docs example. Set US_ELI_GOVINFO_API_KEY (or reuse
# US_ELI_API_KEY - both api.data.gov families accept the same free key).
DEFAULT_START_DATE = "1900-01-01T00:00:00Z"


class GovInfoClient:
    """Async client for the GovInfo API. Use as ``async with GovInfoClient(api_key=...) as c: ...``."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_GOVINFO_BASE_URL,
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

    async def __aenter__(self) -> GovInfoClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(self, path: str, params: dict[str, str], *, category: str) -> dict:
        url = f"{self.base_url}{path}"
        req_params = {**params, "api_key": self._api_key}
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

    async def list_packages(
        self,
        collection: str,
        start_date: str = DEFAULT_START_DATE,
        limit: int = 20,
    ) -> list[dict]:
        """List packages in ``collection`` (e.g. ``"USCODE"``, ``"CFR"``, ``"FR"``)
        modified since ``start_date`` (ISO 8601 UTC).
        """
        data = await self._get_json(
            f"/collections/{collection}/{start_date}",
            {"offsetMark": "*", "pageSize": str(limit)},
            category="search",
        )
        return data.get("packages", [])[:limit]

    async def get_package_summary(self, package_id: str) -> dict:
        """Fetch metadata + content-format links for one package (e.g. ``USCODE-2023-title50``)."""
        data = await self._get_json(f"/packages/{package_id}/summary", {}, category="act")
        return data
