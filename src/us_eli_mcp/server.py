"""FastMCP entry point - US federal legislative process (Congress.gov) and
enacted-law full text (GovInfo) tools.

Run:

    python -m us_eli_mcp.server

Configuration via env:

- ``US_ELI_API_KEY`` (required for real use - free key from https://api.congress.gov/sign-up/;
  falls back to the shared, rate-limited ``DEMO_KEY`` for quick local testing only)
- ``US_ELI_GOVINFO_API_KEY`` (same api.data.gov key family; reuses ``US_ELI_API_KEY``
  if unset, since both Congress.gov and GovInfo accept the same free key)
- ``US_ELI_CACHE_DIR`` (default ``~/.matematic/cache/us-eli``)
- ``US_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``US_ELI_BASE_URL`` (default ``https://api.congress.gov/v3``)
- ``US_ELI_GOVINFO_BASE_URL`` (default ``https://api.govinfo.gov``)

Case law is deliberately NOT covered here - two existing MIT-licensed MCP
servers already wrap CourtListener (``blakeox/courtlistener-mcp``,
``john-walkoe/courtlistener_citations_mcp``); building a third would
duplicate existing work rather than fill a real gap. See DISCOVERY.md.
"""

from __future__ import annotations

import dataclasses
import os

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .citations import build_citation, build_govinfo_citation, parse_bill, parse_govinfo_package
from .client import DEFAULT_BASE_URL, CongressClient
from .govinfo_client import DEFAULT_GOVINFO_BASE_URL, DEFAULT_START_DATE, GovInfoClient

INSTRUCTIONS = """\
This MCP server exposes the Congress.gov API (federal legislative PROCESS - bills as they move through committees and floor votes) and the GovInfo API (enacted law text - US Code, Statutes at Large, Federal Register, CFR). It does NOT cover case law - see Hard constraints.

## Call order

1. `us_search_bills` - list bills of a given `congress` (e.g. 118) and `bill_type` (e.g. "hr" = House bill, "s" = Senate bill, "hres", "sres", "hjres", "sjres", "hconres", "sconres").
2. `us_get_bill` - full detail for one bill by `congress`, `bill_type`, `number`, including its `latest_action_text` (current status).
3. `us_list_code_packages` - list enacted-law packages in a GovInfo `collection` (e.g. "USCODE", "CFR", "FR" for Federal Register) modified since a given date.
4. `us_get_code_package` - full metadata + content-format download links for one package by its `package_id`.

## Hard constraints

- **No free-text keyword search for bills** - the Congress.gov API filters by congress/type/number, not keywords. Use `us_search_bills` to discover candidate `number`s.
- **No case law in this server** - two existing MIT MCP servers already wrap CourtListener for US case law (`blakeox/courtlistener-mcp`, `john-walkoe/courtlistener_citations_mcp`); use one of those instead of expecting case-law tools here.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user (e.g. "H.R. 1, 118th Congress", linking to congress.gov; or a GovInfo package title + collection + date, linking to govinfo.gov).
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/us-eli-mcp.jsonl`.
- **API key** - set `US_ELI_API_KEY` (bills) and optionally `US_ELI_GOVINFO_API_KEY` (GovInfo packages, reuses `US_ELI_API_KEY` if unset) to a free key from api.congress.gov. Without it, the server falls back to the shared `DEMO_KEY`, which has a much lower rate limit and is not suitable for production use.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range.
- `not_found` - no bill or package exists for the given identifiers.
- `upstream_error` - a Congress.gov or GovInfo API error (HTTP, timeout, rate limit). Retry once before surfacing.

## Response style

- Cite bills as `human_readable_citation`: "H.R. 1, 118th Congress".
- Cite GovInfo packages as `human_readable_citation`: "{title}, {collection}, {date_issued}".
- NEVER invent a congress number, bill type/number, or package id - take each from the tool output.
"""


class ToolError(Exception):
    """Structured error for us-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({"invalid_arg", "not_found", "upstream_error"})

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown ToolError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,
)

mcp: FastMCP = FastMCP(name="us-eli-mcp", instructions=INSTRUCTIONS)

_VALID_TYPES = frozenset({"hr", "s", "hres", "sres", "hjres", "sjres", "hconres", "sconres"})


def _base_url() -> str:
    return os.environ.get("US_ELI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    return os.environ.get("US_ELI_API_KEY", "DEMO_KEY")


def _govinfo_base_url() -> str:
    return os.environ.get("US_ELI_GOVINFO_BASE_URL", DEFAULT_GOVINFO_BASE_URL).rstrip("/")


def _govinfo_api_key() -> str:
    return os.environ.get("US_ELI_GOVINFO_API_KEY") or _api_key()


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching bill found in the Congress.gov API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"Congress.gov API error: {type(exc).__name__}: {exc}")
    return exc


def _map_govinfo_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching package found in the GovInfo API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"GovInfo API error: {type(exc).__name__}: {exc}")
    return exc


def _to_dict(b) -> dict:
    citation = build_citation(b)
    return {**dataclasses.asdict(b), **dataclasses.asdict(citation)}


def _to_govinfo_dict(p) -> dict:
    citation = build_govinfo_citation(p)
    return {**dataclasses.asdict(p), **dataclasses.asdict(citation)}


def _check_bill_type(bill_type: str) -> str:
    normalized = bill_type.lower()
    if normalized not in _VALID_TYPES:
        raise ToolError(
            "invalid_arg",
            f"bill_type={bill_type!r} must be one of {sorted(_VALID_TYPES)}.",
        )
    return normalized


# ---------------------------------------------------------------------------
# us_search_bills
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_search_bills(congress: int, bill_type: str, limit: int = 20) -> dict:
    """List US federal bills of a given congress and bill type.

    Args:
        congress: e.g. ``118`` (2023-2024 session).
        bill_type: one of ``"hr"``, ``"s"``, ``"hres"``, ``"sres"``, ``"hjres"``,
            ``"sjres"``, ``"hconres"``, ``"sconres"``.
        limit: max results (default 20, API caps around 250).

    Returns:
        ``{"total": int, "items": [...]}`` - each item carries the citation contract.
    """
    audit = _audit()
    bill_type = _check_bill_type(bill_type)
    if not 1 <= congress <= 200:
        raise ToolError("invalid_arg", f"congress={congress} is out of range (1..200).")
    input_hash = hash_input({"congress": congress, "bill_type": bill_type, "limit": limit})

    with timer() as t:
        try:
            async with CongressClient(api_key=_api_key(), base_url=_base_url()) as client:
                raw_items = await client.list_bills(congress, bill_type, limit)
        except Exception as exc:
            audit.log(tool="us_search_bills", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    items = [_to_dict(parse_bill(r)) for r in raw_items]
    audit.log(tool="us_search_bills", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# us_get_bill
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_get_bill(congress: int, bill_type: str, number: int) -> dict:
    """Fetch full detail (including latest action/status) for one bill.

    Args:
        congress: e.g. ``118``.
        bill_type: e.g. ``"hr"``.
        number: bill number, e.g. ``1``.

    Returns:
        A dict with ``congress``, ``bill_type``, ``number``, ``title``,
        ``latest_action_text``, ``latest_action_date``, ``lex_uri``,
        ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    bill_type = _check_bill_type(bill_type)
    if not 1 <= congress <= 200:
        raise ToolError("invalid_arg", f"congress={congress} is out of range (1..200).")
    if number <= 0:
        raise ToolError("invalid_arg", f"number={number} must be positive.")
    input_hash = hash_input({"congress": congress, "bill_type": bill_type, "number": number})

    with timer() as t:
        try:
            async with CongressClient(api_key=_api_key(), base_url=_base_url()) as client:
                raw = await client.get_bill(congress, bill_type, number)
        except Exception as exc:
            audit.log(tool="us_get_bill", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    if not raw:
        raise ToolError("not_found", f"No bill {bill_type.upper()} {number} in congress {congress}.")
    result = _to_dict(parse_bill(raw))
    audit.log(tool="us_get_bill", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# us_list_code_packages
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_list_code_packages(
    collection: str, start_date: str = DEFAULT_START_DATE, limit: int = 20
) -> dict:
    """List enacted-law packages in a GovInfo collection modified since a given date.

    Args:
        collection: a GovInfo collection code, e.g. ``"USCODE"`` (United States Code),
            ``"CFR"`` (Code of Federal Regulations), ``"FR"`` (Federal Register),
            ``"STATUTE"`` (Statutes at Large).
        start_date: ISO 8601 UTC timestamp (e.g. ``"2023-01-01T00:00:00Z"``); only
            packages modified on/after this date are returned.
        limit: max results (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - each item carries the citation contract.
    """
    audit = _audit()
    if not collection or not collection.strip():
        raise ToolError("invalid_arg", "collection must be a non-empty string.")
    if limit <= 0:
        raise ToolError("invalid_arg", f"limit={limit} must be positive.")
    input_hash = hash_input({"collection": collection, "start_date": start_date, "limit": limit})

    with timer() as t:
        try:
            async with GovInfoClient(
                api_key=_govinfo_api_key(), base_url=_govinfo_base_url()
            ) as client:
                raw_items = await client.list_packages(collection, start_date, limit)
        except Exception as exc:
            audit.log(tool="us_list_code_packages", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_govinfo_upstream(exc) from exc

    items = [_to_govinfo_dict(parse_govinfo_package(r, collection)) for r in raw_items]
    audit.log(tool="us_list_code_packages", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# us_get_code_package
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_get_code_package(package_id: str) -> dict:
    """Fetch metadata and content-format download links for one GovInfo package.

    Args:
        package_id: a GovInfo package id, e.g. ``"USCODE-2023-title50"`` or a
            Federal Register document id - take these from `us_list_code_packages`.

    Returns:
        A dict with ``package_id``, ``collection``, ``title``, ``date_issued``,
        ``congress``, ``last_modified``, ``package_link``, ``download_links``
        (format -> URL, e.g. ``"pdf"``, ``"xml"``, ``"txt"``),
        ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if not package_id or not package_id.strip():
        raise ToolError("invalid_arg", "package_id must be a non-empty string.")
    input_hash = hash_input({"package_id": package_id})

    with timer() as t:
        try:
            async with GovInfoClient(
                api_key=_govinfo_api_key(), base_url=_govinfo_base_url()
            ) as client:
                raw = await client.get_package_summary(package_id)
        except Exception as exc:
            audit.log(tool="us_get_code_package", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_govinfo_upstream(exc) from exc

    if not raw:
        raise ToolError("not_found", f"No GovInfo package found for id {package_id!r}.")
    result = _to_govinfo_dict(parse_govinfo_package(raw, raw.get("collectionCode", "")))
    audit.log(tool="us_get_code_package", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
