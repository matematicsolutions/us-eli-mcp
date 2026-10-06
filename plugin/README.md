# us-eli-mcp - Claude plugin

US law with verifiable citations, as a Claude plugin. It runs the
[us-eli-mcp](https://github.com/matematicsolutions/us-eli-mcp) MCP server, version 0.5.3
from PyPI. `server/uv.lock` pins that package and every dependency with hashes, and the
plugin starts it with `uv run --frozen`, so it runs exactly what was reviewed. Every
answer carries the official source, so a citation can be checked instead of trusted.

What it covers: bills (Congress.gov API), US Code and other GovInfo packages, Federal Register documents, eCFR sections with their version history, and case law search and opinions from CourtListener (Free Law Project). The full tool list is in the
[main README](https://github.com/matematicsolutions/us-eli-mcp#readme).

## Requirements

Claude Code or the Claude desktop app, and [uv](https://docs.astral.sh/uv/) on your
machine (it installs the locked packages on first start and runs the server).

## Install

```
/plugin marketplace add matematicsolutions/us-eli-mcp
/plugin install us-eli-mcp@us-eli-mcp
```

## Data

The server runs on your machine. Each tool call sends your query to the public source it names (api.congress.gov, api.govinfo.gov, federalregister.gov, ecfr.gov or courtlistener.com)
and to nothing else; nothing goes to MateMatic. Your query and the results also pass
through whatever model you use, the same way as any other message.

Congress.gov and GovInfo require an api.data.gov key. Without one the server uses the shared, rate-limited `DEMO_KEY`, which is enough to try it. For regular use, get a free key at https://api.congress.gov/sign-up/ and set `US_ELI_API_KEY` in your environment before you start Claude; the plugin does not ask for it or store it. The Federal Register, eCFR and CourtListener need no key.

The standalone server can fetch a small configuration file (updated source addresses) from
this repository's GitHub Releases on first use. The plugin turns that off
(`US_ELI_RUNTIME_URL` set to empty in `plugin.json`), so it runs only the reviewed code with
its built-in source addresses and makes no request other than the tool calls above.

Two things are written locally, in your home directory:

- a response cache (`~/.matematic/cache/us-eli`), so a repeated lookup does not hit
  the source again. Court decisions are public records and can name the parties.
- an audit log (`~/.matematic/audit/us-eli-mcp.jsonl`), one line per tool call: the
  tool name, a SHA-256 hash of the input (not the input itself), result size, time
  and status.

Delete either folder at any time; `US_ELI_CACHE_DIR` and `US_ELI_AUDIT_DIR` move them.

## Licence

Apache-2.0, see the repository's [LICENSE](https://github.com/matematicsolutions/us-eli-mcp/blob/main/LICENSE).
