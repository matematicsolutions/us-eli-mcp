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
- ``US_ELI_FR_BASE_URL`` (default ``https://www.federalregister.gov/api/v1``, keyless)
- ``US_ELI_COURTLISTENER_BASE_URL`` (default ``https://www.courtlistener.com/api/rest/v4``, keyless)
- ``US_ELI_ECFR_BASE_URL`` (default ``https://www.ecfr.gov/api``, keyless)

Case law scope (feature-003): the CourtListener tools here exist primarily
for STATE case law, which no other source in this connector covers (GovInfo
has none). Federal case law overlaps with existing MIT-licensed CourtListener
MCP wrappers (``blakeox/courtlistener-mcp``,
``john-walkoe/courtlistener_citations_mcp``) - see SOURCES.md for the
anti-duplication reasoning.
"""

from __future__ import annotations

import dataclasses
import os

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .citations import (
    build_case_law_citation,
    build_citation,
    build_ecfr_citation,
    build_federal_register_citation,
    build_govinfo_citation,
    parse_bill,
    parse_case_law_opinion,
    parse_ecfr_section_hit,
    parse_ecfr_version,
    parse_federal_register_doc,
    parse_govinfo_package,
)
from .client import DEFAULT_BASE_URL, CongressClient
from .courtlistener_client import DEFAULT_COURTLISTENER_BASE_URL, CourtListenerClient
from .ecfr_client import DEFAULT_ECFR_BASE_URL, EcfrClient
from .federal_register_client import (
    DEFAULT_FR_BASE_URL,
    VALID_DOC_TYPES,
    VALID_PRESIDENTIAL_TYPES,
    FederalRegisterClient,
)
from .govinfo_client import DEFAULT_GOVINFO_BASE_URL, DEFAULT_START_DATE, GovInfoClient

INSTRUCTIONS = """\
This MCP server exposes five US legal sources: the Congress.gov API (federal legislative PROCESS - bills as they move through committees and floor votes), the GovInfo API (enacted law text - US Code, Statutes at Large, CFR annual editions), the Federal Register API (rules, proposed rules, notices, presidential documents - full-text search since 1994), the CourtListener search API (case law - the headline value is STATE courts, which no other tool here covers), and the eCFR API (the CURRENT Code of Federal Regulations - section-level search and amendment history).

## Call order

1. `us_search_bills` - list bills of a given `congress` (e.g. 118) and `bill_type` (e.g. "hr" = House bill, "s" = Senate bill, "hres", "sres", "hjres", "sjres", "hconres", "sconres").
2. `us_get_bill` - full detail for one bill by `congress`, `bill_type`, `number`, including its `latest_action_text` (current status).
3. `us_list_code_packages` - list enacted-law packages in a GovInfo `collection` (e.g. "USCODE", "CFR", "FR" for Federal Register) modified since a given date.
4. `us_get_code_package` - full metadata + content-format download links for one package by its `package_id`.
5. `us_search_federal_register` - full-text search over Federal Register documents; filter by `doc_type` ("RULE", "PRORULE", "NOTICE", "PRESDOCU") and/or `presidential_document_type` ("executive_order", "proclamation", ...) for executive orders and other presidential documents.
6. `us_get_federal_register_doc` - full metadata for one FR document by its `document_number` (e.g. "2026-13726"), including the official FR citation and a raw-text URL.
7. `us_search_case_law` - full-text search over 8M+ US court opinions; use `court` to scope (e.g. "cal" = California Supreme Court, "ny" = NY Court of Appeals, "scotus"). STATE case law is the reason this tool exists here.
8. `us_get_case` - one opinion cluster by `cluster_id` (take it from `us_search_case_law`).
9. `us_search_cfr_sections` - full-text search over the CURRENT CFR (eCFR, amended through days ago - unlike the GovInfo annual editions).
10. `us_get_cfr_section_history` - amendment history of one CFR section by `title`, `part`, `section` (e.g. 15, "744", "744.3").

## Hard constraints

- **No free-text keyword search for bills** - the Congress.gov API filters by congress/type/number, not keywords. Use `us_search_bills` to discover candidate `number`s.
- **Case-law rate limit** - the CourtListener search endpoint is anonymous and rate-limited to ~5 requests/min. Batch your questions; do not loop over it.
- **Federal case law nuance** - `us_search_case_law` covers federal courts too, but for federal ENACTED law prefer the GovInfo/Federal Register tools; dedicated CourtListener MCP wrappers exist for heavy federal case-law work.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user (e.g. "H.R. 1, 118th Congress"; "91 FR 41591"; "People v. Miranda-Guerrero, 519 P.3d 1004 (California Supreme Court 2022)"; "15 CFR § 744.3").
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/us-eli-mcp.jsonl`.
- **API key** - set `US_ELI_API_KEY` (bills) and optionally `US_ELI_GOVINFO_API_KEY` (GovInfo packages, reuses `US_ELI_API_KEY` if unset) to a free key from api.congress.gov. Without it, the server falls back to the shared `DEMO_KEY`, which has a much lower rate limit and is not suitable for production use. The Federal Register, CourtListener and eCFR tools are keyless - no configuration needed.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range.
- `not_found` - no bill, package, document, case or section exists for the given identifiers.
- `upstream_error` - an upstream API error (HTTP, timeout, rate limit). Retry once before surfacing; for `us_search_case_law`, wait ~15s first (anonymous rate limit).

## Response style

- Cite bills as `human_readable_citation`: "H.R. 1, 118th Congress".
- Cite GovInfo packages as `human_readable_citation`: "{title}, {collection}, {date_issued}".
- Cite Federal Register documents by their official citation: "{title}, 91 FR 41591, 2026-07-07".
- Cite cases by reporter citation when present: "{case_name}, {reporter} ({court} {year})"; the tool falls back to the docket number when no reporter citation exists - never invent one.
- Cite CFR sections as "{title} CFR § {section}".
- NEVER invent a congress number, bill number, package id, FR document number, cluster_id, reporter citation, or CFR section - take each from the tool output.
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


def _fr_base_url() -> str:
    return os.environ.get("US_ELI_FR_BASE_URL", DEFAULT_FR_BASE_URL).rstrip("/")


def _courtlistener_base_url() -> str:
    return os.environ.get("US_ELI_COURTLISTENER_BASE_URL", DEFAULT_COURTLISTENER_BASE_URL).rstrip("/")


def _ecfr_base_url() -> str:
    return os.environ.get("US_ELI_ECFR_BASE_URL", DEFAULT_ECFR_BASE_URL).rstrip("/")


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


def _map_fr_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching document found in the Federal Register API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError(
            "upstream_error", f"Federal Register API error: {type(exc).__name__}: {exc}"
        )
    return exc


def _map_courtlistener_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching opinion found in the CourtListener API.")
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return ToolError(
            "upstream_error",
            "CourtListener anonymous rate limit hit (~5 requests/min) - wait ~15s and retry.",
        )
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError(
            "upstream_error", f"CourtListener API error: {type(exc).__name__}: {exc}"
        )
    return exc


def _map_ecfr_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching CFR section found in the eCFR API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"eCFR API error: {type(exc).__name__}: {exc}")
    return exc


def _to_dict(b) -> dict:
    citation = build_citation(b)
    return {**dataclasses.asdict(b), **dataclasses.asdict(citation)}


def _to_govinfo_dict(p) -> dict:
    citation = build_govinfo_citation(p)
    return {**dataclasses.asdict(p), **dataclasses.asdict(citation)}


def _to_fr_dict(d) -> dict:
    citation = build_federal_register_citation(d)
    return {**dataclasses.asdict(d), **dataclasses.asdict(citation)}


def _to_case_dict(o) -> dict:
    citation = build_case_law_citation(o)
    return {**dataclasses.asdict(o), **dataclasses.asdict(citation)}


def _to_ecfr_dict(h) -> dict:
    citation = build_ecfr_citation(h)
    return {**dataclasses.asdict(h), **dataclasses.asdict(citation)}


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


# ---------------------------------------------------------------------------
# us_search_federal_register
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_search_federal_register(
    term: str,
    doc_type: str | None = None,
    presidential_document_type: str | None = None,
    limit: int = 20,
) -> dict:
    """Full-text search over Federal Register documents (1994-present, keyless).

    Args:
        term: full-text search query, e.g. ``"artificial intelligence"``.
        doc_type: optional filter - one of ``"RULE"``, ``"PRORULE"`` (proposed rule),
            ``"NOTICE"``, ``"PRESDOCU"`` (presidential document).
        presidential_document_type: optional filter for presidential documents -
            e.g. ``"executive_order"``, ``"proclamation"``, ``"memorandum"``.
        limit: max results (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - ``total`` is the API's own count
        (display-capped at 10 000); each item carries the citation contract.
    """
    audit = _audit()
    if not term or not term.strip():
        raise ToolError("invalid_arg", "term must be a non-empty string.")
    if doc_type and doc_type.upper() not in VALID_DOC_TYPES:
        raise ToolError(
            "invalid_arg", f"doc_type={doc_type!r} must be one of {sorted(VALID_DOC_TYPES)}."
        )
    if presidential_document_type and presidential_document_type not in VALID_PRESIDENTIAL_TYPES:
        raise ToolError(
            "invalid_arg",
            f"presidential_document_type={presidential_document_type!r} must be one of "
            f"{sorted(VALID_PRESIDENTIAL_TYPES)}.",
        )
    if limit <= 0:
        raise ToolError("invalid_arg", f"limit={limit} must be positive.")
    input_hash = hash_input(
        {"term": term, "doc_type": doc_type, "pres": presidential_document_type, "limit": limit}
    )

    with timer() as t:
        try:
            async with FederalRegisterClient(base_url=_fr_base_url()) as client:
                total, raw_items = await client.search_documents(
                    term,
                    doc_type.upper() if doc_type else None,
                    presidential_document_type,
                    limit,
                )
        except Exception as exc:
            audit.log(tool="us_search_federal_register", input_hash=input_hash,
                      output_count_or_size=0, duration_ms=t.duration_ms if t.duration_ms else 0,
                      status="error", error=f"{type(exc).__name__}: {exc}")
            raise _map_fr_upstream(exc) from exc

    items = [_to_fr_dict(parse_federal_register_doc(r)) for r in raw_items]
    audit.log(tool="us_search_federal_register", input_hash=input_hash,
              output_count_or_size=len(items), duration_ms=t.duration_ms, status="ok")
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# us_get_federal_register_doc
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_get_federal_register_doc(document_number: str) -> dict:
    """Fetch full metadata for one Federal Register document.

    Args:
        document_number: an FR document number, e.g. ``"2026-13726"`` - take it
            from `us_search_federal_register`.

    Returns:
        A dict with ``document_number``, ``title``, ``doc_type``, ``abstract``,
        ``publication_date``, ``agencies``, ``fr_citation`` (the official
        citation, e.g. ``"91 FR 41591"``), ``raw_text_url``, ``pdf_url``,
        ``executive_order_number``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if not document_number or not document_number.strip():
        raise ToolError("invalid_arg", "document_number must be a non-empty string.")
    input_hash = hash_input({"document_number": document_number})

    with timer() as t:
        try:
            async with FederalRegisterClient(base_url=_fr_base_url()) as client:
                raw = await client.get_document(document_number)
        except Exception as exc:
            audit.log(tool="us_get_federal_register_doc", input_hash=input_hash,
                      output_count_or_size=0, duration_ms=t.duration_ms if t.duration_ms else 0,
                      status="error", error=f"{type(exc).__name__}: {exc}")
            raise _map_fr_upstream(exc) from exc

    if not raw or not raw.get("document_number"):
        raise ToolError("not_found", f"No Federal Register document {document_number!r}.")
    result = _to_fr_dict(parse_federal_register_doc(raw))
    audit.log(tool="us_get_federal_register_doc", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# us_search_case_law
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_search_case_law(query: str, court: str | None = None, limit: int = 20) -> dict:
    """Full-text search over 8M+ US court opinions (CourtListener, keyless).

    The headline value is STATE case law - no other tool in this server covers
    state courts. Federal courts are searchable too, but dedicated
    CourtListener MCP wrappers exist for heavy federal case-law work.

    Args:
        query: full-text query, e.g. ``"negligence standard of care"``.
        court: optional CourtListener court id to scope the search, e.g.
            ``"cal"`` (California Supreme Court), ``"ny"`` (NY Court of
            Appeals), ``"texapp"`` (Texas Court of Appeals), ``"scotus"``.
        limit: max results (default 20; the API returns 20 per page).

    Returns:
        ``{"total": int, "items": [...]}`` - ``total`` is the API's own count;
        each item carries the citation contract (real reporter citation when
        one exists, docket number otherwise - never a fabricated one).
    """
    audit = _audit()
    if not query or not query.strip():
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    if limit <= 0:
        raise ToolError("invalid_arg", f"limit={limit} must be positive.")
    input_hash = hash_input({"query": query, "court": court, "limit": limit})

    with timer() as t:
        try:
            async with CourtListenerClient(base_url=_courtlistener_base_url()) as client:
                total, raw_items = await client.search_opinions(query, court, limit)
        except Exception as exc:
            audit.log(tool="us_search_case_law", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_courtlistener_upstream(exc) from exc

    items = [_to_case_dict(parse_case_law_opinion(r)) for r in raw_items]
    audit.log(tool="us_search_case_law", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# us_get_case
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_get_case(cluster_id: int) -> dict:
    """Fetch one opinion cluster by its CourtListener ``cluster_id``.

    Uses the keyless search endpoint with a ``cluster_id:{id}`` field query
    (the authenticated ``/clusters/{id}/`` endpoint is deliberately not used).

    Args:
        cluster_id: e.g. ``8512159`` - take it from `us_search_case_law`.

    Returns:
        A dict with ``cluster_id``, ``case_name``, ``court``, ``court_id``,
        ``date_filed``, ``docket_number``, ``citations`` (reporter citations),
        ``status``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if cluster_id <= 0:
        raise ToolError("invalid_arg", f"cluster_id={cluster_id} must be positive.")
    input_hash = hash_input({"cluster_id": cluster_id})

    with timer() as t:
        try:
            async with CourtListenerClient(base_url=_courtlistener_base_url()) as client:
                raw = await client.get_opinion_cluster(cluster_id)
        except Exception as exc:
            audit.log(tool="us_get_case", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_courtlistener_upstream(exc) from exc

    if raw is None:
        raise ToolError("not_found", f"No opinion cluster {cluster_id} in CourtListener.")
    result = _to_case_dict(parse_case_law_opinion(raw))
    audit.log(tool="us_get_case", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# us_search_cfr_sections
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_search_cfr_sections(query: str, limit: int = 20) -> dict:
    """Full-text search over the CURRENT Code of Federal Regulations (eCFR, keyless).

    Unlike the GovInfo ``CFR`` collection (annual-edition snapshots), the eCFR
    is amended through days ago and every hit carries the exact CFR hierarchy
    (title/part/section) plus an excerpt.

    Args:
        query: full-text query, e.g. ``"unmanned aircraft"``.
        limit: max results (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - ``total`` is the API's own count
        (display-capped at 10 000); each item carries the citation contract
        (``"{title} CFR § {section}"`` + the public ecfr.gov section page).
    """
    audit = _audit()
    if not query or not query.strip():
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    if limit <= 0:
        raise ToolError("invalid_arg", f"limit={limit} must be positive.")
    input_hash = hash_input({"query": query, "limit": limit})

    with timer() as t:
        try:
            async with EcfrClient(base_url=_ecfr_base_url()) as client:
                total, raw_items = await client.search_sections(query, limit)
        except Exception as exc:
            audit.log(tool="us_search_cfr_sections", input_hash=input_hash,
                      output_count_or_size=0, duration_ms=t.duration_ms if t.duration_ms else 0,
                      status="error", error=f"{type(exc).__name__}: {exc}")
            raise _map_ecfr_upstream(exc) from exc

    items = [_to_ecfr_dict(parse_ecfr_section_hit(r)) for r in raw_items]
    audit.log(tool="us_search_cfr_sections", input_hash=input_hash,
              output_count_or_size=len(items), duration_ms=t.duration_ms, status="ok")
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# us_get_cfr_section_history
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def us_get_cfr_section_history(title: int, part: str, section: str) -> dict:
    """Fetch the amendment history (point-in-time versions) of one CFR section.

    Args:
        title: CFR title number, e.g. ``15``.
        part: part identifier, e.g. ``"744"``.
        section: section identifier, e.g. ``"744.3"`` - take title/part/section
            from `us_search_cfr_sections`.

    Returns:
        ``{"total": int, "items": [...]}`` - each item is one version with
        ``date``, ``amendment_date``, ``name``, ``substantive``, ``removed``.
    """
    audit = _audit()
    if not 1 <= title <= 50:
        raise ToolError("invalid_arg", f"title={title} is out of range (1..50).")
    if not part or not part.strip():
        raise ToolError("invalid_arg", "part must be a non-empty string.")
    if not section or not section.strip():
        raise ToolError("invalid_arg", "section must be a non-empty string.")
    input_hash = hash_input({"title": title, "part": part, "section": section})

    with timer() as t:
        try:
            async with EcfrClient(base_url=_ecfr_base_url()) as client:
                raw_items = await client.get_section_versions(title, part, section)
        except Exception as exc:
            audit.log(tool="us_get_cfr_section_history", input_hash=input_hash,
                      output_count_or_size=0, duration_ms=t.duration_ms if t.duration_ms else 0,
                      status="error", error=f"{type(exc).__name__}: {exc}")
            raise _map_ecfr_upstream(exc) from exc

    if not raw_items:
        raise ToolError(
            "not_found", f"No versions for {title} CFR § {section} (part {part}) in the eCFR API."
        )
    items = [dataclasses.asdict(parse_ecfr_version(r)) for r in raw_items]
    audit.log(tool="us_get_cfr_section_history", input_hash=input_hash,
              output_count_or_size=len(items), duration_ms=t.duration_ms, status="ok")
    return {"total": len(items), "items": items}


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
