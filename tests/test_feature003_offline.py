"""Offline parse tests for feature-003 (Federal Register, CourtListener, eCFR)
against fixtures captured live from each API on 2026-07-07. No network."""

from __future__ import annotations

import json
from pathlib import Path

from us_eli_mcp.citations import (
    build_case_law_citation,
    build_ecfr_citation,
    build_federal_register_citation,
    parse_case_law_opinion,
    parse_ecfr_section_hit,
    parse_ecfr_version,
    parse_federal_register_doc,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_fr_search_result() -> None:
    data = _load("fr_search.json")
    assert data["count"] > 0
    doc = parse_federal_register_doc(data["results"][0])
    assert doc.document_number
    assert doc.html_url.startswith("https://www.federalregister.gov/documents/")
    citation = build_federal_register_citation(doc)
    assert citation.lex_uri == (
        f"https://www.federalregister.gov/api/v1/documents/{doc.document_number}.json"
    )
    assert citation.source_url == doc.html_url
    assert doc.document_number in citation.human_readable_citation or (
        doc.fr_citation and doc.fr_citation in citation.human_readable_citation
    )


def test_parse_fr_document_detail() -> None:
    doc = parse_federal_register_doc(_load("fr_document.json"))
    assert doc.document_number == "2026-13726"
    assert doc.fr_citation == "91 FR 41591"
    assert doc.raw_text_url is not None
    citation = build_federal_register_citation(doc)
    # The official FR citation, never a fabricated label, once the API gives one.
    assert "91 FR 41591" in citation.human_readable_citation


def test_parse_case_law_search_result() -> None:
    data = _load("courtlistener_search.json")
    assert data["count"] > 0
    opinion = parse_case_law_opinion(data["results"][0])
    assert opinion.cluster_id > 0
    assert opinion.court_id == "cal"
    citation = build_case_law_citation(opinion)
    assert citation.source_url.startswith("https://www.courtlistener.com/opinion/")
    assert f"cluster_id:{opinion.cluster_id}" in citation.lex_uri
    if opinion.citations:
        # A real reporter citation from the API, verbatim.
        assert opinion.citations[0] in citation.human_readable_citation
    elif opinion.docket_number:
        assert opinion.docket_number in citation.human_readable_citation


def test_case_law_citation_no_reporter_falls_back_to_docket() -> None:
    opinion = parse_case_law_opinion(
        {
            "cluster_id": 4515328,
            "caseName": "Contract Decor, Inc.",
            "court": "Armed Services Board of Contract Appeals",
            "court_id": "asbca",
            "dateFiled": "2018-06-25",
            "docketNumber": "61489",
            "citation": [],
            "absolute_url": "/opinion/4515328/contract-decor-inc/",
        }
    )
    citation = build_case_law_citation(opinion)
    assert "No. 61489" in citation.human_readable_citation
    assert "2018" in citation.human_readable_citation


def test_parse_ecfr_search_hit() -> None:
    data = _load("ecfr_search.json")
    hit = parse_ecfr_section_hit(data["results"][0])
    assert hit.title == "15"
    assert hit.section == "744.3"
    citation = build_ecfr_citation(hit)
    assert citation.human_readable_citation.startswith("15 CFR § 744.3")
    assert citation.source_url == "https://www.ecfr.gov/current/title-15/part-744/section-744.3"


def test_parse_ecfr_versions() -> None:
    data = _load("ecfr_versions.json")
    versions = [parse_ecfr_version(v) for v in data["content_versions"]]
    assert len(versions) >= 1
    assert versions[0].identifier == "744.3"
    assert versions[0].date
