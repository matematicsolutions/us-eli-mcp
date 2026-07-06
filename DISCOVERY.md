# Discovery notes - USA

Date: 2026-07-06.

## v0.2.0 - GovInfo added (enacted law text); CourtListener tried and reverted

Date: 2026-07-06 (same day, second pass - cross-fleet audit found this
connector had zero case-law/full-text coverage, one gap common to all four
non-EU connectors probed that day: IL, US, GB, BR).

**CourtListener was implemented, then reverted.** A live probe confirmed
CourtListener v4's `/search/` endpoint works anonymously and is a real,
broad case-law source. But this connector's own "Why this connector
originally stopped at Congress.gov bills" section (below) had ALREADY made
a considered decision not to build a CourtListener wrapper here, because
`blakeox/courtlistener-mcp` (MIT, 49 tools) and
`john-walkoe/courtlistener_citations_mcp` (MIT) already do exactly that. A
concurrent multi-agent session momentarily built and shipped a CourtListener
integration anyway, overriding that decision without re-litigating it - on
review this was reverted, because "the gap is real" does not override "two
MIT projects already fill it"; the original reasoning still holds. If you
want US case law via MCP, use one of those two existing servers instead of
expecting it here.

**GovInfo was built instead** - the gap this connector's own DISCOVERY.md
already named as the natural v0.2 feature (see below), and one genuinely not
covered elsewhere in this fleet:

```
GET https://api.govinfo.gov/collections/{collection}/{startDate}?offsetMark=*&pageSize=N&api_key=...
GET https://api.govinfo.gov/packages/{packageId}/summary?api_key=...
```

Same api.data.gov key family as Congress.gov (`US_ELI_GOVINFO_API_KEY`,
falling back to `US_ELI_API_KEY`, falling back to `DEMO_KEY`). Covers US Code,
Statutes at Large, Federal Register, and CFR collections - full enacted-law
text, not just the legislative process `us_search_bills`/`us_get_bill` track.

New tools:

- `us_list_code_packages(collection, start_date, limit=20)` - list packages
  in a GovInfo collection (e.g. `"USCODE"`, `"CFR"`, `"FR"`) modified since a
  date.
- `us_get_code_package(package_id)` - metadata + content-format download
  links (pdf/xml/txt) for one package.

Both tools follow the exact conventions already established for
`us_search_bills`/`us_get_bill`: `ToolAnnotations(readOnlyHint=True, ...)`,
`ToolError` with the same three codes, `AuditLogger`/`hash_input`/`timer()`
audit logging to the same JSONL file, `HttpCache`-backed caching via a new
`GovInfoClient` (`govinfo_client.py`, mirroring `CongressClient`'s
retry/backoff logic), and a `GovInfoPackage`/citation-contract dataclass pair
in `models.py`/`citations.py` parallel to `Bill`/`Citation`.

**Known transient issue, not a code defect**: `tests/test_govinfo_smoke.py`
hit a `429 Too Many Requests` on `DEMO_KEY` during this session, because the
same shared key was hammered repeatedly across several concurrent discovery
probes earlier in the day. `DEMO_KEY`'s rate limit resets on its own; this is
not evidence of a broken endpoint (the 400/500 errors seen earlier in
discovery were a URL-shape issue, since fixed - see the request shapes
above, both live-verified with a 200 once the rate limit was clear).

Version bumped 0.1.0 -> 0.2.0 (minor, per semver: new backward-compatible
tools, no breaking changes to `us_search_bills`/`us_get_bill`).

## Why this connector originally stopped at Congress.gov bills

The US legal-data landscape is more fragmented than the EU/Brazil pattern
this fleet otherwise follows - there is no single agency that owns
legislation + case law end to end (compare Finlex, or NeuRIS in Germany).
Three separate, already-mature pieces exist:

1. **Congress.gov** (this connector) - the legislative process, confirmed
   live with `DEMO_KEY`, JSON, stable per-bill URL. Building this first is
   the highest-value, lowest-effort slice.
2. **GovInfo** - enacted law text, same api.data.gov key family, separate
   package/granule identifier scheme. Natural v0.2 feature for this repo -
   not built in this original pass (kept the first release reviewable);
   built in the v0.2.0 update above.
3. **CourtListener / Free Law Project** (case law) - `blakeox/courtlistener-mcp`
   (MIT) and `john-walkoe/courtlistener_citations_mcp` (MIT) already exist and
   are reasonably mature. A live-probe in an earlier sweep (2026-07-04) found
   that CourtListener's citation-validation logic lives server-side (requires
   a token + network call, breaking the zero-cloud pattern this fleet
   otherwise favors); the one genuinely portable piece - a Jaccard
   name-mismatch heuristic - was already ported into `citation-grounding-pl`
   v2.1. Building a third CourtListener wrapper here would duplicate two
   existing MIT projects instead of filling a real gap.

## Caselaw Access Project (case.law) - discontinued as a live API

Harvard's Caselaw Access Project shut down its own API and search in March
2024 (Harvard Library Innovation Lab blog, 2024-03-26) after the licensing
restriction from the original Ravel Law/LexisNexis agreement expired. The raw
bulk data (6.6M cases, CC0) now lives as a static Parquet dataset on Hugging
Face; the live search/API layer was handed to CourtListener. There is no
separate "CAP connector" left to build - it is the same CourtListener
ecosystem referenced above.

## DEMO_KEY caveat

`DEMO_KEY` works for both Congress.gov and GovInfo (both api.data.gov-hosted)
but is rate-limited and shared across every user of the public docs example -
fine for development, not for production traffic. Set `US_ELI_API_KEY` to
your own free key before real use.
