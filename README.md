# us-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/us-eli-mcp -->

MCP server for US law with verifiable citations. Five sources behind ten
read-only tools:

- **Congress.gov API** - the federal legislative *process*: bills as they move
  through committees and floor votes.
- **GovInfo API** - enacted law text as published packages: US Code, Statutes
  at Large, CFR annual editions, Federal Register issues.
- **Federal Register API** - full-text search over 1,003,504 FR documents
  (1994-2026, live-verified 2026-07-07), including 8,513 presidential
  documents (1,550 executive orders). Keyless.
- **CourtListener search API** - full-text search over 8,294,123 court
  opinions (live-verified 2026-07-07). The headline value is STATE case law
  (California, New York, Texas, ...), which no federal source covers. Keyless,
  ~5 requests/min anonymous.
- **eCFR API** - the CURRENT Code of Federal Regulations: section-level
  full-text search over 412,846 sections plus per-section amendment history.
  Keyless.

## What this is not

- **State legislation** (all 50 states) - see [LegiScan](https://legiscan.com/legiscan),
  a free-tier aggregator (30,000 queries/month) not wrapped here.
- **A federal case-law workhorse** - for heavy federal case-law research the
  mature MIT-licensed wrappers
  ([blakeox/courtlistener-mcp](https://github.com/blakeox/courtlistener-mcp),
  john-walkoe/courtlistener_citations_mcp) remain the recommendation; the
  case-law tools here exist primarily for state courts. See SOURCES.md.

## Tools

| Tool | Purpose |
|---|---|
| `us_search_bills` | List bills by congress (e.g. `118`) and type (`hr`, `s`, `hres`, ...) |
| `us_get_bill` | Full detail + latest action for one bill |
| `us_list_code_packages` | List GovInfo packages in a collection (`USCODE`, `CFR`, `FR`, `STATUTE`) |
| `us_get_code_package` | Metadata + download links (PDF/XML/TXT) for one package |
| `us_search_federal_register` | Full-text search over FR documents; filter rules, notices, executive orders |
| `us_get_federal_register_doc` | One FR document with its official citation (e.g. `91 FR 41591`) |
| `us_search_case_law` | Full-text search over 8M+ opinions; `court` filter (e.g. `cal`, `ny`, `scotus`) |
| `us_get_case` | One opinion cluster by `cluster_id` |
| `us_search_cfr_sections` | Full-text search over the current CFR (eCFR) |
| `us_get_cfr_section_history` | Amendment history of one CFR section (e.g. 15 CFR 744.3) |

Every response carries `lex_uri` (a resolvable API URL), `human_readable_citation`
(the official convention: `"H.R. 1, 118th Congress"`, `"91 FR 41591"`,
`"People v. Miranda-Guerrero, 519 P.3d 1004 (California Supreme Court 2022)"`,
`"15 CFR § 744.3"`) and `source_url` (the public page). Reporter citations are
taken verbatim from the source and never fabricated; when none exists the
docket number is used instead.

## Install

```bash
pip install us-eli-mcp
```


### Windows 11 with Smart App Control

Smart App Control blocks unsigned executables, which covers `uvx.exe`, `pip.exe`
and the `us-eli-mcp.exe` launcher that pip writes at install time. The `python.exe` and
`py.exe` from the python.org installer are signed by the Python Software
Foundation, so running the module through the interpreter works:

```bash
python -m pip install us-eli-mcp
python -m us_eli_mcp
```

`pip.exe` is blocked for the same reason, so install with `python -m pip`, not
`pip install`. If `python` is not on PATH, use the Windows launcher: `py -3 -m us_eli_mcp`.

```json
{ "mcpServers": { "us-eli-mcp": { "command": "python", "args": ["-m", "us_eli_mcp"] } } }
```

Do not turn Smart App Control off to work around this - it cannot be re-enabled
without reinstalling Windows.

## Configuration

| Env var | Default |
|---|---|
| `US_ELI_API_KEY` | `DEMO_KEY` (shared, low rate limit - get your own free key at [api.congress.gov/sign-up](https://api.congress.gov/sign-up/)) |
| `US_ELI_GOVINFO_API_KEY` | reuses `US_ELI_API_KEY` (same api.data.gov key family) |
| `US_ELI_CACHE_DIR` | `~/.matematic/cache/us-eli` |
| `US_ELI_AUDIT_DIR` | `~/.matematic/audit` |
| `US_ELI_BASE_URL` | `https://api.congress.gov/v3` |
| `US_ELI_GOVINFO_BASE_URL` | `https://api.govinfo.gov` |
| `US_ELI_FR_BASE_URL` | `https://www.federalregister.gov/api/v1` (keyless) |
| `US_ELI_COURTLISTENER_BASE_URL` | `https://www.courtlistener.com/api/rest/v4` (keyless) |
| `US_ELI_ECFR_BASE_URL` | `https://www.ecfr.gov/api` (keyless) |

The Federal Register, CourtListener and eCFR tools need no key at all.

## License

Apache-2.0 (code). Congress.gov, GovInfo, Federal Register and eCFR data are
US government works (public domain). CourtListener data is provided by the
Free Law Project.
