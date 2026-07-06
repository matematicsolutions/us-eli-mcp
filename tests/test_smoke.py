"""Live smoke test against the real Congress.gov API (DEMO_KEY). Network required."""

from __future__ import annotations

import pytest

from us_eli_mcp.citations import build_citation, parse_bill
from us_eli_mcp.client import CongressClient


@pytest.mark.asyncio
async def test_search_and_get_bill() -> None:
    async with CongressClient(api_key="DEMO_KEY") as client:
        raw_items = await client.list_bills(118, "hr", limit=3)
        assert len(raw_items) == 3

        first = parse_bill(raw_items[0])
        citation = build_citation(first)
        assert citation.human_readable_citation.startswith("H.R. ")
        assert citation.lex_uri.startswith("https://api.congress.gov/v3/bill/")
        assert citation.source_url.startswith("https://www.congress.gov/bill/")

        detail_raw = await client.get_bill(118, "hr", 1)
        detail = parse_bill(detail_raw)
        assert detail.congress == 118
        assert detail.title is not None
