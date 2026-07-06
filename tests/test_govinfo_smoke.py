"""Live smoke test against the real GovInfo API (DEMO_KEY). Network required."""

from __future__ import annotations

import pytest

from us_eli_mcp.citations import build_govinfo_citation, parse_govinfo_package
from us_eli_mcp.govinfo_client import GovInfoClient


@pytest.mark.asyncio
async def test_list_and_get_package() -> None:
    async with GovInfoClient(api_key="DEMO_KEY") as client:
        raw_items = await client.list_packages("USCODE", limit=3)
        assert len(raw_items) > 0

        first = parse_govinfo_package(raw_items[0], "USCODE")
        citation = build_govinfo_citation(first)
        assert first.package_id
        assert citation.source_url.startswith("https://www.govinfo.gov/content/pkg/")
        assert citation.lex_uri.startswith("https://api.govinfo.gov/packages/")

        detail_raw = await client.get_package_summary(first.package_id)
        detail = parse_govinfo_package(detail_raw, "USCODE")
        assert detail.package_id == first.package_id
