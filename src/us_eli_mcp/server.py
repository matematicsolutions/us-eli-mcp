"""FastMCP entry point - US federal legislative process (Congress.gov) tools.

Run:

    python -m us_eli_mcp.server

Configuration via env:

- ``US_ELI_API_KEY`` (required for real use - free key from https://api.congress.gov/sign-up/;
  falls back to the shared, rate-limited ``DEMO_KEY`` for quick local testing only)
- ``US_ELI_CACHE_DIR`` (default ``~/.matematic/cache/us-eli``)
- ``US_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``US_ELI_BASE_URL`` (default ``https://api.congress.gov/v3``)
"""

from __future__ import annotations

import dataclasses
import os

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .citations import build_citation, parse_bill
from .client import DEFAULT_BASE_URL, CongressClient

INSTRUCTIONS = """\
This MCP server exposes the Congress.gov API. It tracks the US federal legislative PROCESS - bills as they move through committees and floor votes - not a consolidated database of already-enacted law text (that lives at GovInfo/US Code, not covered here).

## Call order

1. `us_search_bills` - list bills of a given `congress` (e.g. 118) and `bill_type` (e.g. "hr" = House bill, "s" = Senate bill, "hres", "sres", "hjres", "sjres", "hconres", "sconres").
2. `us_get_bill` - full detail for one bill by `congress`, `bill_type`, `number`, including its `latest_action_text` (current status).

## Hard constraints

- **No free-text keyword search** - the API filters by congress/type/number, not keywords. Use `us_search_bills` to discover candidate `number`s.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user (e.g. "H.R. 1, 118th Congress", linking to congress.gov).
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/us-eli-mcp.jsonl`.
- **API key** - set `US_ELI_API_KEY` to a free key from api.congress.gov. Without it, the server falls back to the shared `DEMO_KEY`, which has a much lower rate limit and is not suitable for production use.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range.
- `not_found` - no bill exists for that congress/type/number.
- `upstream_error` - a Congress.gov API error (HTTP, timeout, rate limit). Retry once before surfacing.

## Response style

- Cite bills as `human_readable_citation`: "H.R. 1, 118th Congress".
- NEVER invent a congress number, bill type or number - take each from the tool output.
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


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching bill found in the Congress.gov API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"Congress.gov API error: {type(exc).__name__}: {exc}")
    return exc


def _to_dict(b) -> dict:
    citation = build_citation(b)
    return {**dataclasses.asdict(b), **dataclasses.asdict(citation)}


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


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
