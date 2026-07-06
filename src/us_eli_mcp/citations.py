"""Citation contract for us-eli-mcp.

Congress.gov has no formal ELI/ECLI-style identifier, but it does give every
bill a stable, resolvable API URL and a canonical public congress.gov page -
we use those instead of fabricating anything. Same approach for GovInfo
packages (US Code / CFR / Federal Register): no formal ELI, but every
package has a stable ``packageId``, a resolvable API summary URL, and a
canonical public govinfo.gov content page.
"""

from __future__ import annotations

from typing import Any

from .models import Bill, Citation, GovInfoPackage

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
