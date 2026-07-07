"""Async httpx client for the Federal Register API (www.federalregister.gov/api/v1).

The Federal Register API is keyless JSON (no api.data.gov key at all) and is
NOT a duplicate of the GovInfo ``FR`` collection this connector already lists:
GovInfo exposes whole daily-issue *packages* by modification date, with no
document-level search. This API adds full-text search over every individual
FR document since 1994, type filters (rule / proposed rule / notice /
presidential document), and the official Federal Register citation
(e.g. ``91 FR 41591``) per document. Presidential documents (executive
orders, proclamations) are a document-type filter on the same endpoint, so
one client covers both the Federal Register and presidential-documents
sources.

Endpoint shapes below were live-verified against www.federalregister.gov
(2026-07-07):

- ``/documents.json`` - search; ``conditions[term]`` (full text),
  ``conditions[type][]`` (``RULE``, ``PRORULE``, ``NOTICE``, ``PRESDOCU``),
  ``conditions[presidential_document_type][]`` (``executive_order``,
  ``proclamation``, ...). The top-level ``count`` field is the true total
  up to a display cap of 10 000; the unfiltered corpus total comes from
  ``/documents/facets/yearly`` (1 003 504 documents across 1994-2026 at
  the time of the live check).
- ``/documents/{document_number}.json`` - full metadata for one document,
  including ``citation``, ``raw_text_url``, ``executive_order_number``.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_FR_BASE_URL = "https://www.federalregister.gov/api/v1"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "us-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/us-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# Explicit field list for search results - without it the list endpoint omits
# the official FR citation and the presidential-document fields.
_SEARCH_FIELDS = (
    "document_number",
    "title",
    "type",
    "abstract",
    "publication_date",
    "agencies",
    "citation",
    "html_url",
    "pdf_url",
    "raw_text_url",
    "executive_order_number",
    "presidential_document_number",
)

VALID_DOC_TYPES = frozenset({"RULE", "PRORULE", "NOTICE", "PRESDOCU"})
VALID_PRESIDENTIAL_TYPES = frozenset(
    {
        "determination",
        "executive_order",
        "memorandum",
        "notice",
        "proclamation",
        "presidential_order",
        "other",
    }
)


class FederalRegisterClient:
    """Async client. Use as ``async with FederalRegisterClient() as c: ...`` (keyless)."""

    def __init__(
        self,
        base_url: str = DEFAULT_FR_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> FederalRegisterClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(
        self, path: str, params: list[tuple[str, str]], *, category: str
    ) -> dict:
        url = f"{self.base_url}{path}"
        cache_key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params))
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

    async def search_documents(
        self,
        term: str,
        doc_type: str | None = None,
        presidential_document_type: str | None = None,
        limit: int = 20,
    ) -> tuple[int, list[dict]]:
        """Full-text search over Federal Register documents.

        Returns ``(total_count, results)`` - ``total_count`` is the API's own
        ``count`` field (display-capped at 10 000), not ``len(results)``.
        """
        params: list[tuple[str, str]] = [
            ("per_page", str(limit)),
            ("conditions[term]", term),
        ]
        params.extend(("fields[]", f) for f in _SEARCH_FIELDS)
        if doc_type:
            params.append(("conditions[type][]", doc_type))
        if presidential_document_type:
            params.append(
                ("conditions[presidential_document_type][]", presidential_document_type)
            )
        data = await self._get_json("/documents.json", params, category="search")
        return int(data.get("count", 0)), data.get("results", [])[:limit]

    async def get_document(self, document_number: str) -> dict:
        """Fetch full metadata for one document (e.g. ``"2026-13726"``)."""
        return await self._get_json(f"/documents/{document_number}.json", [], category="act")
