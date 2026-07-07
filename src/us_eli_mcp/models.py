"""Plain dataclasses mirroring the Congress.gov bill, GovInfo package,
Federal Register document, CourtListener opinion and eCFR section JSON shapes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bill:
    congress: int
    bill_type: str
    number: str
    title: str | None
    latest_action_text: str | None
    latest_action_date: str | None
    api_url: str


@dataclass(frozen=True)
class Citation:
    lex_uri: str
    human_readable_citation: str
    source_url: str


@dataclass(frozen=True)
class GovInfoPackage:
    package_id: str
    collection: str
    title: str | None
    date_issued: str | None
    congress: int | None
    last_modified: str | None
    package_link: str
    download_links: dict[str, str]


@dataclass(frozen=True)
class FederalRegisterDoc:
    document_number: str
    title: str | None
    doc_type: str | None
    abstract: str | None
    publication_date: str | None
    agencies: list[str]
    fr_citation: str | None
    html_url: str
    pdf_url: str | None
    raw_text_url: str | None
    executive_order_number: str | None
    presidential_document_number: str | None


@dataclass(frozen=True)
class CaseLawOpinion:
    cluster_id: int
    case_name: str | None
    court: str | None
    court_id: str | None
    date_filed: str | None
    docket_number: str | None
    citations: list[str]
    status: str | None
    absolute_url: str


@dataclass(frozen=True)
class EcfrSectionHit:
    title: str | None
    part: str | None
    section: str | None
    heading: str | None
    excerpt: str | None
    starts_on: str | None
    ends_on: str | None


@dataclass(frozen=True)
class EcfrVersion:
    identifier: str
    name: str | None
    date: str | None
    amendment_date: str | None
    title: str | None
    part: str | None
    substantive: bool
    removed: bool
