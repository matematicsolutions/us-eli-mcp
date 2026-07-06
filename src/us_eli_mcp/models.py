"""Plain dataclasses mirroring the Congress.gov bill JSON shape."""

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
