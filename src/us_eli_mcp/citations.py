"""Citation contract for us-eli-mcp.

Congress.gov has no formal ELI/ECLI-style identifier, but it does give every
bill a stable, resolvable API URL and a canonical public congress.gov page -
we use those instead of fabricating anything. Same approach for GovInfo
packages (US Code / CFR / Federal Register): no formal ELI, but every
package has a stable ``packageId``, a resolvable API summary URL, and a
canonical public govinfo.gov content page. Federal Register documents carry
the OFFICIAL citation form (e.g. ``91 FR 41591``); case-law opinions carry a
real reporter citation when one exists (never a fabricated one); CFR sections
use the standard ``{title} CFR § {section}`` form.
"""

from __future__ import annotations

from typing import Any

from .models import (
    Bill,
    CaseLawOpinion,
    Citation,
    EcfrSectionHit,
    EcfrVersion,
    FederalRegisterDoc,
    GovInfoPackage,
)

_PREFIX = {
    "hr": ("H.R.", "house-bill"),
    "s": ("S.", "senate-bill"),
    "hres": ("H.Res.", "house-resolution"),
    "sres": ("S.Res.", "senate-resolution"),
    "hjres": ("H.J.Res.", "house-joint-resolution"),
    "sjres": ("S.J.Res.", "senate-joint-resolution"),
    "hconres": ("H.Con.Res.", "house-concurrent-resolution"),
    "sconres": ("S.Con.Res.", "senate-concurrent-resolution"),
}

_PUBLIC_URL = "https://www.congress.gov/bill/{congress}th-congress/{slug}/{number}"


def parse_bill(raw: dict[str, Any]) -> Bill:
    latest = raw.get("latestAction") or {}
    congress = raw["congress"]
    bill_type = raw["type"].lower()
    number = str(raw["number"])
    # The list endpoint includes `url`; the single-bill detail endpoint does not.
    api_url = raw.get("url") or (
        f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{number}?format=json"
    )
    return Bill(
        congress=congress,
        bill_type=bill_type,
        number=number,
        title=raw.get("title"),
        latest_action_text=latest.get("text"),
        latest_action_date=latest.get("actionDate"),
        api_url=api_url,
    )


def build_citation(b: Bill) -> Citation:
    prefix, slug = _PREFIX.get(b.bill_type, (b.bill_type.upper(), b.bill_type))
    human = f"{prefix} {b.number}, {b.congress}th Congress"
    source_url = _PUBLIC_URL.format(congress=b.congress, slug=slug, number=b.number)
    return Citation(lex_uri=b.api_url, human_readable_citation=human, source_url=source_url)


_GOVINFO_PUBLIC_URL = "https://www.govinfo.gov/content/pkg/{package_id}/"
_GOVINFO_API_URL = "https://api.govinfo.gov/packages/{package_id}/summary"


def parse_govinfo_package(raw: dict, collection: str) -> GovInfoPackage:
    """Parse a package dict, either from a ``/collections/{c}/{date}`` list item
    (fields: ``packageId``, ``title``, ``dateIssued``, ``lastModified``,
    ``packageLink``, ``congress``) or a ``/packages/{id}/summary`` detail
    response (same field names, plus a ``download`` dict of format links).
    """
    package_id = raw.get("packageId") or raw.get("package_id") or ""
    download = raw.get("download") or {}
    return GovInfoPackage(
        package_id=package_id,
        collection=raw.get("docClass") or collection,
        title=raw.get("title"),
        date_issued=raw.get("dateIssued"),
        congress=raw.get("congress"),
        last_modified=raw.get("lastModified"),
        package_link=raw.get("packageLink") or _GOVINFO_API_URL.format(package_id=package_id),
        download_links=dict(download),
    )


def build_govinfo_citation(p: GovInfoPackage) -> Citation:
    """Citation contract for a GovInfo package: no formal ELI, but a stable
    ``packageId``, a resolvable API summary URL, and a canonical public
    govinfo.gov content page.
    """
    lex_uri = _GOVINFO_API_URL.format(package_id=p.package_id)
    source_url = _GOVINFO_PUBLIC_URL.format(package_id=p.package_id)
    parts = [p.title, p.collection, p.date_issued]
    human = ", ".join(str(part) for part in parts if part)
    return Citation(lex_uri=lex_uri, human_readable_citation=human, source_url=source_url)


# ---------------------------------------------------------------------------
# Federal Register (www.federalregister.gov API)
# ---------------------------------------------------------------------------

_FR_API_URL = "https://www.federalregister.gov/api/v1/documents/{document_number}.json"


def parse_federal_register_doc(raw: dict[str, Any]) -> FederalRegisterDoc:
    """Parse a document dict, either from a ``/documents.json`` search result
    (explicit ``fields[]`` requested by the client) or a
    ``/documents/{number}.json`` detail response (same field names).
    """
    agencies = [
        a.get("name") or a.get("raw_name") or ""
        for a in (raw.get("agencies") or [])
        if isinstance(a, dict)
    ]
    eo = raw.get("executive_order_number")
    pres = raw.get("presidential_document_number")
    return FederalRegisterDoc(
        document_number=str(raw.get("document_number") or ""),
        title=raw.get("title"),
        doc_type=raw.get("type"),
        abstract=raw.get("abstract"),
        publication_date=raw.get("publication_date"),
        agencies=[a for a in agencies if a],
        fr_citation=raw.get("citation"),
        html_url=raw.get("html_url") or "",
        pdf_url=raw.get("pdf_url"),
        raw_text_url=raw.get("raw_text_url"),
        executive_order_number=str(eo) if eo else None,
        presidential_document_number=str(pres) if pres else None,
    )


def build_federal_register_citation(d: FederalRegisterDoc) -> Citation:
    """Citation contract for a Federal Register document: the official FR
    citation (e.g. ``"91 FR 41591"``) when present, the stable document
    number otherwise; the API detail URL as ``lex_uri`` and the public
    federalregister.gov page as ``source_url``.
    """
    lex_uri = _FR_API_URL.format(document_number=d.document_number)
    label = d.fr_citation or f"FR Doc. {d.document_number}"
    if d.executive_order_number:
        label = f"Executive Order {d.executive_order_number}, {label}"
    parts = [d.title, label, d.publication_date]
    human = ", ".join(str(part) for part in parts if part)
    return Citation(lex_uri=lex_uri, human_readable_citation=human, source_url=d.html_url)


# ---------------------------------------------------------------------------
# CourtListener case law (courtlistener.com API)
# ---------------------------------------------------------------------------

_CL_API_URL = "https://www.courtlistener.com/api/rest/v4/search/?q=cluster_id:{cluster_id}&type=o"
_CL_PUBLIC_BASE = "https://www.courtlistener.com"


def parse_case_law_opinion(raw: dict[str, Any]) -> CaseLawOpinion:
    """Parse one ``/search/?type=o`` result (an opinion cluster)."""
    citations = [str(c) for c in (raw.get("citation") or []) if c]
    return CaseLawOpinion(
        cluster_id=int(raw.get("cluster_id") or 0),
        case_name=raw.get("caseName"),
        court=raw.get("court"),
        court_id=raw.get("court_id"),
        date_filed=raw.get("dateFiled"),
        docket_number=raw.get("docketNumber"),
        citations=citations,
        status=raw.get("status"),
        absolute_url=raw.get("absolute_url") or "",
    )


def build_case_law_citation(o: CaseLawOpinion) -> Citation:
    """Citation contract for a case-law opinion: the first reporter citation
    when one exists (e.g. ``"519 P.3d 1004"``), the docket number otherwise -
    never a fabricated reporter reference.
    """
    lex_uri = _CL_API_URL.format(cluster_id=o.cluster_id)
    reporter = o.citations[0] if o.citations else None
    ref = reporter or (f"No. {o.docket_number}" if o.docket_number else f"cluster {o.cluster_id}")
    year = o.date_filed[:4] if o.date_filed else None
    tail = f"({o.court} {year})" if o.court and year else f"({o.court or year or ''})".strip("()")
    human = ", ".join(p for p in [o.case_name, ref] if p)
    if tail:
        human = f"{human} {tail}"
    source_url = f"{_CL_PUBLIC_BASE}{o.absolute_url}" if o.absolute_url else _CL_PUBLIC_BASE
    return Citation(lex_uri=lex_uri, human_readable_citation=human, source_url=source_url)


# ---------------------------------------------------------------------------
# eCFR (www.ecfr.gov API)
# ---------------------------------------------------------------------------

_ECFR_VERSIONS_URL = (
    "https://www.ecfr.gov/api/versioner/v1/versions/title-{title}.json"
    "?part={part}&section={section}"
)
_ECFR_SECTION_URL = "https://www.ecfr.gov/current/title-{title}/part-{part}/section-{section}"
_ECFR_PART_URL = "https://www.ecfr.gov/current/title-{title}/part-{part}"


def parse_ecfr_section_hit(raw: dict[str, Any]) -> EcfrSectionHit:
    """Parse one ``/search/v1/results`` hit - the CFR hierarchy lives in
    ``hierarchy`` (identifiers) and ``headings`` (display names).
    """
    hierarchy = raw.get("hierarchy") or {}
    headings = raw.get("headings") or {}
    return EcfrSectionHit(
        title=hierarchy.get("title"),
        part=hierarchy.get("part"),
        section=hierarchy.get("section"),
        heading=headings.get("section") or headings.get("part"),
        excerpt=raw.get("full_text_excerpt"),
        starts_on=raw.get("starts_on"),
        ends_on=raw.get("ends_on"),
    )


def build_ecfr_citation(h: EcfrSectionHit) -> Citation:
    """Citation contract for a CFR section: the standard ``{title} CFR
    S {section}`` form, the versions API URL as ``lex_uri`` and the public
    ecfr.gov section page as ``source_url``.
    """
    if h.section:
        human = f"{h.title} CFR § {h.section}"
        source_url = _ECFR_SECTION_URL.format(title=h.title, part=h.part, section=h.section)
        lex_uri = _ECFR_VERSIONS_URL.format(title=h.title, part=h.part, section=h.section)
    else:
        human = f"{h.title} CFR Part {h.part}"
        source_url = _ECFR_PART_URL.format(title=h.title, part=h.part)
        lex_uri = source_url
    if h.heading:
        human = f"{human} ({h.heading})"
    return Citation(lex_uri=lex_uri, human_readable_citation=human, source_url=source_url)


def parse_ecfr_version(raw: dict[str, Any]) -> EcfrVersion:
    """Parse one entry of a ``/versioner/v1/versions/title-{n}.json`` response."""
    return EcfrVersion(
        identifier=str(raw.get("identifier") or ""),
        name=raw.get("name"),
        date=raw.get("date"),
        amendment_date=raw.get("amendment_date"),
        title=raw.get("title"),
        part=raw.get("part"),
        substantive=bool(raw.get("substantive")),
        removed=bool(raw.get("removed")),
    )
