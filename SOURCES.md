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

## CourtListener API (`courtlistener.com`, Free Law Project)

- **Origin**: Free Law Project, a 501(c)(3) non-profit.
- **License/access**: public REST API v4. The `/search/` endpoint is
  anonymous/keyless (confirmed live 2026-07-06); rate-limited to roughly
  5 requests/min for anonymous callers. The single-item `/opinions/{id}/`,
  `/clusters/{id}/`, and `/dockets/{id}/` endpoints require authentication
  (confirmed live 2026-07-06) - not used by this connector.
- **Access**: REST, JSON.
- **Coverage**: this connector calls `/api/rest/v4/search/?q=...&type=o`
  (optionally `&court=<id>`) for `us_search_case_law`, and the same endpoint
  scoped by a `cluster_id:{id}` field query for `us_get_case`. ~1M+ opinions,
  covers both federal and state courts.

## Not covered (out of scope for this connector)

- **GovInfo API** (`api.govinfo.gov`) - enacted law text (US Code, Statutes at
  Large, Federal Register), package/granule identifier scheme, also a free
  api.data.gov key. Natural next connector in this family.
- **LegiScan** (`legiscan.com/legiscan`) - the only aggregator covering
  legislation for all 50 states; free tier caps at 30,000 queries/month.
