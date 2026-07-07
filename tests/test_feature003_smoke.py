"""Live smoke tests for feature-003 (Federal Register, CourtListener, eCFR).
Network required. All three APIs are keyless.

CourtListener's anonymous rate limit is ~5 requests/min - the case-law test
makes exactly two calls and sleeps between them.
"""

from __future__ import annotations

import anyio
import pytest

from us_eli_mcp.citations import (
    build_case_law_citation,
    build_ecfr_citation,
    build_federal_register_citation,
    parse_case_law_opinion,
    parse_ecfr_section_hit,
    parse_federal_register_doc,
)
from us_eli_mcp.courtlistener_client import CourtListenerClient
from us_eli_mcp.ecfr_client import EcfrClient
from us_eli_mcp.federal_register_client import FederalRegisterClient


@pytest.mark.asyncio
async def test_federal_register_search_and_get() -> None:
    async with FederalRegisterClient() as client:
        total, raw_items = await client.search_documents(
            "artificial intelligence", doc_type="PRESDOCU", limit=3
        )
        assert total > 0
        assert len(raw_items) > 0

        first = parse_federal_register_doc(raw_items[0])
        citation = build_federal_register_citation(first)
        assert citation.source_url.startswith("https://www.federalregister.gov/documents/")

        detail_raw = await client.get_document(first.document_number)
        detail = parse_federal_register_doc(detail_raw)
        assert detail.document_number == first.document_number
        assert detail.fr_citation  # official "N FR page" citation on the detail response


@pytest.mark.asyncio
async def test_case_law_search_and_get() -> None:
    async with CourtListenerClient() as client:
        total, raw_items = await client.search_opinions("negligence", court="cal", limit=3)
        assert total > 0
        assert len(raw_items) > 0

        first = parse_case_law_opinion(raw_items[0])
        assert first.court_id == "cal"
        citation = build_case_law_citation(first)
        assert citation.source_url.startswith("https://www.courtlistener.com/opinion/")

        await anyio.sleep(15)  # anonymous rate limit ~5 req/min

        detail_raw = await client.get_opinion_cluster(first.cluster_id)
        assert detail_raw is not None
        detail = parse_case_law_opinion(detail_raw)
        assert detail.cluster_id == first.cluster_id


@pytest.mark.asyncio
async def test_ecfr_search_and_history() -> None:
    async with EcfrClient() as client:
        total, raw_items = await client.search_sections("unmanned aircraft", limit=3)
        assert total > 0
        assert len(raw_items) > 0

        first = parse_ecfr_section_hit(raw_items[0])
        citation = build_ecfr_citation(first)
        assert "CFR" in citation.human_readable_citation
        assert citation.source_url.startswith("https://www.ecfr.gov/current/title-")

        versions = await client.get_section_versions(15, "744", "744.3")
        assert len(versions) >= 1
        assert versions[0].get("identifier") == "744.3"
