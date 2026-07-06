# us-eli-mcp

MCP server for the Congress.gov API. Tracks the US federal legislative
*process* - bills as they move through committees and floor votes.

## What this is not

This connector does not cover:

- **Enacted law text** - the US Code and Statutes at Large live at GovInfo
  (`api.govinfo.gov`), a separate API with its own package/granule identifier
  scheme. Not implemented here yet.
- **State legislation** (all 50 states) - see [LegiScan](https://legiscan.com/legiscan),
  a free-tier aggregator (30,000 queries/month) not wrapped here yet.
- **Case law** - [CourtListener](https://www.courtlistener.com/) already has
  mature, permissively-licensed MCP wrappers
  ([blakeox/courtlistener-mcp](https://github.com/blakeox/courtlistener-mcp), MIT).
  Building a third one would be redundant; see DISCOVERY.md.

## Tools

| Tool | Purpose |
|---|---|
| `us_search_bills` | List bills by congress (e.g. `118`) and type (`hr`, `s`, `hres`, ...) |
| `us_get_bill` | Full detail + latest action for one bill |

Every response carries `lex_uri` (the Congress.gov API URL for the bill),
`human_readable_citation` (e.g. `"H.R. 1, 118th Congress"`) and `source_url`
(the public congress.gov page).

## Install

```bash
pip install us-eli-mcp
```

## Configuration

| Env var | Default |
|---|---|
| `US_ELI_API_KEY` | `DEMO_KEY` (shared, low rate limit - get your own free key at [api.congress.gov/sign-up](https://api.congress.gov/sign-up/)) |
| `US_ELI_CACHE_DIR` | `~/.matematic/cache/us-eli` |
| `US_ELI_AUDIT_DIR` | `~/.matematic/audit` |
| `US_ELI_BASE_URL` | `https://api.congress.gov/v3` |

## License

Apache-2.0 (code). Congress.gov data is US government work (public domain).
