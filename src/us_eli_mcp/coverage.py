"""Element 9 of the MateMatic MCP canon: this connector declares its own coverage.

Knowledge about what a corpus does NOT hold is useless while it lives only as prose
in the server instructions - the model has to remember it and choose to relay it, and
an agent has no way to ask. Here it is callable.

Every gap below is grounded in this connector's own source and tool surface. The list
is deliberately never empty: no legal corpus is complete, so an empty gap list would
mean "nobody checked", not "there are no gaps".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _CoverageBase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CoverageFamily(_CoverageBase):
    """One data family this connector exposes."""

    name: str = Field(description="Data family, e.g. 'Federal legislation'.")
    tool: str = Field(description="Tool or tools that reach this family.")
    source: str = Field(description="Official source the data comes from.")
    captured_at: str | None = Field(
        default=None,
        description="Date this family was last captured (ISO). None when queried live.",
    )
    live: bool = Field(default=True, description="True when queried live instead of from a snapshot.")


class CoverageGap(_CoverageBase):
    """A known, named hole in this connector's coverage - plus the way around it."""

    id: str = Field(description="Stable gap identifier.")
    family: str = Field(description="Which family the gap belongs to.")
    missing: str = Field(description="What is NOT available through this connector.")
    fallback: str = Field(description="Where to go instead.")


class Coverage(_CoverageBase):
    """What this connector covers, how it is sourced, and what it does not cover."""

    status: Literal["ok", "degraded", "failed"] = "ok"
    as_of_note: str = Field(description="States what the dates mean, and what they do not promise.")
    families: list[CoverageFamily] = Field(default_factory=list)
    known_gaps: list[CoverageGap] = Field(
        default_factory=list,
        description="Never empty. An empty list would mean 'not checked', not 'no gaps'.",
    )


SOURCE = 'Congress.gov, GovInfo, Federal Register, eCFR and CourtListener'

AS_OF_NOTE = (
    "Data is queried live against the source, so there is no local snapshot date. Any date "
    "on a record states when the source published it - not that this connector verified the "
    "text is still in force today."
)

_FAMILIES: list[dict] = [{'name': 'Bills (Congress.gov)', 'tool': 'us_search_bills / us_get_bill'}, {'name': 'Enacted law packages (GovInfo)', 'tool': 'us_list_code_packages / us_get_code_package'}, {'name': 'Federal Register', 'tool': 'us_search_federal_register / us_get_federal_register_doc'}, {'name': 'CFR sections (eCFR)', 'tool': 'us_search_cfr_sections / us_get_cfr_section_history'}, {'name': 'Case law (CourtListener)', 'tool': 'us_search_case_law / us_get_case'}]

_GAPS: list[dict] = [{'id': 'US-001', 'family': 'Bills (Congress.gov)', 'missing': 'No free-text keyword search for bills - the Congress.gov API filters by congress, type and number, not keywords.', 'fallback': 'Discover candidate numbers first, then fetch by coordinate.'}, {'id': 'US-002', 'family': 'Case law (CourtListener)', 'missing': 'The CourtListener search endpoint is anonymous and rate-limited to roughly 5 requests per minute.', 'fallback': 'Batch questions; do not loop over this tool.'}, {'id': 'US-003', 'family': 'Bills (Congress.gov)', 'missing': 'State law is out of scope - all five sources here are federal.', 'fallback': "Use the relevant state's own legislature or court site."}]


def build_coverage() -> Coverage:
    """Assemble the declared coverage for this connector."""
    return Coverage(
        status="ok",
        as_of_note=AS_OF_NOTE,
        families=[CoverageFamily(source=SOURCE, live=True, **f) for f in _FAMILIES],
        known_gaps=[CoverageGap(**g) for g in _GAPS],
    )
