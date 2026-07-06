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

## Not covered (out of scope for this connector)

- **GovInfo API** (`api.govinfo.gov`) - enacted law text (US Code, Statutes at
  Large, Federal Register), package/granule identifier scheme, also a free
  api.data.gov key. Natural next connector in this family.
- **LegiScan** (`legiscan.com/legiscan`) - the only aggregator covering
  legislation for all 50 states; free tier caps at 30,000 queries/month.
- **CourtListener / Free Law Project** (case law) - already has mature,
  permissively-licensed MCP wrappers (see DISCOVERY.md); building another one
  here would duplicate existing work rather than fill a gap.
