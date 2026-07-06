# Discovery notes - USA

Date: 2026-07-06.

## Why this connector stops at Congress.gov bills

The US legal-data landscape is more fragmented than the EU/Brazil pattern
this fleet otherwise follows - there is no single agency that owns
legislation + case law end to end (compare Finlex, or NeuRIS in Germany).
Three separate, already-mature pieces exist:

1. **Congress.gov** (this connector) - the legislative process, confirmed
   live with `DEMO_KEY`, JSON, stable per-bill URL. Building this first is
   the highest-value, lowest-effort slice.
2. **GovInfo** - enacted law text, same api.data.gov key family, separate
   package/granule identifier scheme. Natural v0.2 feature for this repo -
   not built in this pass to keep the first release reviewable.
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
