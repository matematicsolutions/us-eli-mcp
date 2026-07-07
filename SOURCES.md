# Sources

## Congress.gov API (`api.congress.gov`)

- **Origin**: Library of Congress.
- **License**: US government work, public domain. Requires a free api.data.gov
  key (register in ~1 minute); a shared `DEMO_KEY` exists for quick testing
  but has a much lower rate limit.
- **Access**: REST, JSON.
- **Coverage**: this connector only calls `/bill/{congress}/{type}` (list) and
  `/bill/{congress}/{type}/{number}` (detail). It does not cover amendments,
  committees, members, or any other Congress.gov endpoint.
- **LDH note**: Legal Data Hunter marks `US/CongressGov` as `blocked` - that
  refers to bulk scraping of the congress.gov website. The official REST API
  with a free key works fine (live-verified again 2026-07-07) and is what
  this connector uses.

## GovInfo API (`api.govinfo.gov`) - shipped v0.2.0

- **Origin**: US Government Publishing Office.
- **License**: US government work, public domain. Same free api.data.gov key
  family as Congress.gov (reuses `US_ELI_API_KEY` when
  `US_ELI_GOVINFO_API_KEY` is unset).
- **Access**: REST, JSON; package/granule identifier scheme.
- **Coverage**: `/collections/{collection}/{startDate}` (list packages, e.g.
  `USCODE`, `CFR`, `FR`, `STATUTE`) and `/packages/{packageId}/summary`
  (metadata + download links). Tools: `us_list_code_packages`,
  `us_get_code_package`.
- **Limits**: packages are snapshots (e.g. annual CFR editions, daily FR
  issues) with NO document-level full-text search - that is exactly the gap
  the Federal Register API and eCFR API sections below fill.

## Federal Register API (`www.federalregister.gov/api/v1`) - shipped feature-003, v0.3.0

- **Origin**: Office of the Federal Register (NARA) + GPO.
- **License**: US government work, public domain. Keyless - no registration
  at all.
- **Access**: REST, JSON.
- **Coverage**: `/documents.json` (full-text search since 1994, filters for
  `type` = RULE / PRORULE / NOTICE / PRESDOCU and
  `presidential_document_type` = executive_order / proclamation / ...) and
  `/documents/{document_number}.json` (detail incl. the OFFICIAL citation,
  e.g. `91 FR 41591`, and a raw-text URL). Tools:
  `us_search_federal_register`, `us_get_federal_register_doc`.
- **Verified volume (2026-07-07)**: the search `count` field is display-capped
  at 10 000, so the corpus total was re-derived from the dedicated yearly
  facets endpoint
  (`https://www.federalregister.gov/api/v1/documents/facets/yearly`):
  **1 003 504 documents** across 1994-2026. Presidential documents:
  **8 513** (`conditions[type][]=PRESDOCU`, uncapped count), of which
  **1 550** executive orders
  (`conditions[presidential_document_type][]=executive_order`).
- **Duplication check vs GovInfo `FR` collection**: NOT a duplicate. GovInfo
  lists whole daily-issue packages by modification date with no search; this
  API adds document-level full-text search, type filters and the official FR
  citation. One client covers TWO Legal Data Hunter ids (`US/FederalRegister`
  and `US/PresidentialDocuments`).

## CourtListener API (`courtlistener.com`, Free Law Project) - shipped feature-003, v0.3.0

- **Origin**: Free Law Project, a 501(c)(3) non-profit.
- **License/access**: public REST API v4. The `/search/` endpoint is
  anonymous/keyless (confirmed live 2026-07-06 and again 2026-07-07);
  rate-limited to roughly 5 requests/min for anonymous callers. The
  single-item `/opinions/{id}/`, `/clusters/{id}/`, and `/dockets/{id}/`
  endpoints require authentication - not used by this connector.
- **Access**: REST, JSON.
- **Coverage**: this connector calls `/api/rest/v4/search/?q=...&type=o`
  (optionally `&court=<id>`) for `us_search_case_law`, and the same endpoint
  scoped by a `cluster_id:{id}` field query for `us_get_case`.
- **Verified volume (2026-07-07)**: **8 294 123 opinions** - re-derived from
  the API's own `count` field on an unfiltered query
  (`https://www.courtlistener.com/api/rest/v4/search/?type=o`), not from an
  example-query hit count.
- **Scope / anti-duplication (decided 2026-07-06, refined 2026-07-07)**: the
  headline value here is STATE case law - GovInfo has no state case law at
  all, and CourtListener is the only keyless source with millions of
  state-court opinions (e.g. `court=cal`, `ny`, `texapp`). Federal case law
  is searchable through the same endpoint, but for heavy federal case-law
  work the existing MIT-licensed wrappers (`blakeox/courtlistener-mcp`,
  `john-walkoe/courtlistener_citations_mcp`) remain the recommendation; this
  connector does not try to replace them.

## eCFR API (`www.ecfr.gov/api`) - shipped feature-003, v0.3.0

- **Origin**: Office of the Federal Register (NARA) + GPO.
- **License**: US government work, public domain. Keyless.
- **Access**: REST, JSON.
- **Coverage**: `/search/v1/results` (section-level full-text search over the
  CURRENT CFR; every hit carries the exact title/part/section hierarchy and
  an excerpt) and `/versioner/v1/versions/title-{n}.json` (per-section
  amendment history). Tools: `us_search_cfr_sections`,
  `us_get_cfr_section_history`.
- **Verified volume (2026-07-07)**: the search `meta.total_count` field is
  display-capped at 10 000; the per-title counts endpoint
  (`https://www.ecfr.gov/api/search/v1/counts/titles?query=*`) summed to
  **412 846 sections** across all 50 CFR titles (current through 2026-07-02
  per `/versioner/v1/titles.json`).
- **Duplication check vs GovInfo `CFR` collection**: NOT a duplicate. GovInfo
  ships annual-edition snapshot packages with no search and no amendment
  history; the eCFR is amended through days ago and adds both.
- **Known gap at check (2026-07-07)**: the point-in-time full-text endpoint
  `/versioner/v1/full/{date}/title-{n}.xml` returned **503 for every variant
  tried** (with/without subset params, small titles, multiple user agents,
  PowerShell and curl), while search, counts, titles and versions endpoints
  all worked. No tool was built on it - shipping a lookup we could not
  confirm live would defeat the citation-hallucination protection this fleet
  exists for. If it comes back it is the natural full-text extension.

## Not covered (out of scope for this connector)

- **LegiScan** (`legiscan.com/legiscan`) - the only aggregator covering
  legislation for all 50 states; free tier caps at 30,000 queries/month.

---

# Sources ledger - United States (US)

Machine-diffable record of every Legal Data Hunter (`worldwidelaw/legal-sources`) source we have
checked for this country, and what we did about it. Machine-read by `eu-legal-mcp/gap_scan.py`.
One row per LDH source `id`; update on every widen-round.

| LDH id | LDH name | LDH status @ check | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|---|
| US/CongressGov | Congress.gov (Congressional Bills) | blocked | shipped | `us_search_bills`, `us_get_bill` | LDH `blocked` refers to site scraping; the official REST API with a free api.data.gov key works (re-verified live 2026-07-07). Shipped v0.1.0. |
| US/GovInfo | GovInfo (US Federal Legislation) | complete | shipped | `us_list_code_packages`, `us_get_code_package` | shipped feature-002, v0.2.0 (2026-07-06) |
| US/USCode | US Code (Codified Federal Statutes) | complete | shipped | `us_list_code_packages`, `us_get_code_package` | covered by the GovInfo client (`collection="USCODE"`), v0.2.0 |
| US/FederalRegister | Federal Register | complete | shipped | `us_search_federal_register`, `us_get_federal_register_doc` | shipped feature-003, 2026-07-07; 1 003 504 docs (yearly-facets probe) |
| US/PresidentialDocuments | Presidential Documents (Executive Orders, Proclamations) | complete | shipped | `us_search_federal_register` | same client/endpoint as US/FederalRegister (`doc_type="PRESDOCU"`, `presidential_document_type`); 8 513 docs, 1 550 EOs (live 2026-07-07) |
| US/FederalCourts | US Federal Courts (SCOTUS + Circuits) | complete | shipped | `us_search_case_law`, `us_get_case` | one CourtListener client covers all court ids; federal overlap with existing MIT wrappers documented above |
| US/FederalDistrictCourts | US Federal District Courts | complete | shipped | `us_search_case_law`, `us_get_case` | same CourtListener client (`court` filter); 8 294 123 opinions total (live 2026-07-07) |
| US/FederalSpecialtyCourts | US Federal Specialty & Bankruptcy Courts | complete | shipped | `us_search_case_law`, `us_get_case` | same CourtListener client (`court` filter) |
| US/eCFR | eCFR - Electronic Code of Federal Regulations | complete | shipped | `us_search_cfr_sections`, `us_get_cfr_section_history` | shipped feature-003, 2026-07-07; 412 846 sections (counts/titles probe); versioner full.xml 503 at check - no full-text tool |
| US/CaselawAccessProject | Caselaw Access Project (Harvard/HuggingFace) | complete | rejected | - | `duplicate` - CAP's historical corpus was transferred to the Free Law Project and merged into CourtListener's live index, which we ship |
| US/EyeciteCitations | US Case Law Citation Index (Eyecite + CourtListener) | complete | todo | - | citation-graph layer over CourtListener, candidate for a grounding feature |
| US/EveryCRSReport | Congressional Research Service Reports | complete | todo | - | secondary literature, not primary law - low priority for this connector |
| US/TaxCourt | US Tax Court Published Opinions | complete | todo | - | scouted but not built this round |
| US/FTC | US FTC Decisions and Orders | complete | todo | - | scouted but not built this round |

The `LDH status @ check` column records what LDH said WHEN WE CHECKED (2026-07-07 manifest,
2 998 sources / 1 734 complete). LDH flips `blocked -> complete` over time; `gap_scan.py` raises
STALE-REJ on any rejected-by-us + complete-in-LDH pair so rejections get re-verified instead of
trusted forever.

## Status vocabulary

- `shipped` - live in this repo, has at least one MCP tool, tested.
- `rejected` - scouted, deliberately NOT built; `Notes` gives the reason (`bot_protection`,
  `captcha_required`, `geo_restricted`, `duplicate`, `no_full_text_access`,
  `needs_separate_subscription`, `unreliable_exact_match`, ...).
- `todo` - LDH has it as `complete`, we have not evaluated it yet.

## Not on this list

Anything NOT in this table has simply not been checked yet against this country's LDH sources
(the US manifest alone lists 185 sources, including 50-state legislation and courts) - absence is
not a claim of non-existence. Re-run the manifest pull to find genuinely new entries.
