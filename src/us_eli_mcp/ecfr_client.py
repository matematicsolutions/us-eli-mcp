"""Async httpx client for the eCFR API (www.ecfr.gov/api).

The eCFR API is keyless JSON and is NOT a duplicate of the GovInfo ``CFR``
collection this connector already lists: GovInfo exposes annual-edition
snapshot *packages*, with no search and no amendment history. This API adds
section-level full-text search over the CURRENT Code of Federal Regulations
(amended through days ago, not last year's edition) and per-section
point-in-time amendment history.

Endpoint shapes below were live-verified against www.ecfr.gov (2026-07-07):

- ``/api/search/v1/results`` - full-text search; each hit carries the exact
  CFR hierarchy (title/part/section), headings and an excerpt. The
  ``meta.total_count`` field is the true total up to a display cap of 10 000;
  the per-title counts endpoint (``/api/search/v1/counts/titles?query=*``)
  summed to 412 846 sections at the time of the live check.
- ``/api/versioner/v1/versions/title-{n}.json?part=..&section=..`` -
  amendment history (every substantive version) of one section.
- ``/api/versioner/v1/full/{date}/title-{n}.xml`` - full XML of a title at a
  point in time. Returned 503 for every variant tried at the live check
  (2026-07-07), so NO tool here is built on it; if it comes back it would be
  the natural full-text extension.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_ECFR_BASE_URL = "https://www.ecfr.gov/api"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "us-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/us-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class EcfrClient:
    """Async client. Use as ``async with EcfrClient() as c: ...`` (keyless)."""

    def __init__(
        self,
        base_url: str = DEFAULT_ECFR_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> EcfrClient:
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

    async def search_sections(self, query: str, limit: int = 20) -> tuple[int, list[dict]]:
        """Full-text search over current CFR sections.

        Returns ``(total_count, results)`` - ``total_count`` is the API's own
        ``meta.total_count`` field (display-capped at 10 000).
        """
        data = await self._get_json(
            "/search/v1/results",
            {"query": query, "per_page": str(limit)},
            category="search",
        )
        meta = data.get("meta") or {}
        return int(meta.get("total_count", 0)), data.get("results", [])[:limit]

    async def get_section_versions(self, title: int, part: str, section: str) -> list[dict]:
        """Fetch the amendment history of one CFR section (e.g. title 15,
        part ``"744"``, section ``"744.3"``).
        """
        data = await self._get_json(
            f"/versioner/v1/versions/title-{title}.json",
            {"part": part, "section": section},
            category="act",
        )
        return data.get("content_versions", [])
