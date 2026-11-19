# 1. Extract the PxWeb client into its own package

Date: 2026-11-19

## Status

Accepted

## Context

`sistat.pxweb` is a generic client for PxWeb API **v1**: table listing, metadata, Selections resolved by
Folded match, splitting at the Cell limit, Rate limit and retries, json-stat2 to Records. Nothing in it is
specific to SiStat; the SiStat layer only adds the base URL, table-id normalisation and Table search.
There is no maintained Python client for PxWeb v1 that others could use instead.

Keeping it inside `sistat` hides it from anyone using another PxWeb v1 server, and makes the "never imports
from the SiStat layer" rule a convention nothing enforces.

## Decision

Move it to its own repository, `jprevc/pxweb`, published on PyPI as **`pxweb-client`** and imported as
`pxweb` (the `pxweb` name on PyPI is held by an empty placeholder). `sistat` depends on it with
`pxweb-client>=0.1,<0.2`.

- pxweb supports PxWeb API v1 only. v2 is out of scope until there is a reason to add it.
- pxweb owns the errors: `PxWebError`, `APIError`, `QueryError`. `sistat` re-exports them and has no error
  classes of its own; `SiStatError` is removed. A sistat-specific subclass of `PxWebError` is added only if
  the SiStat layer ever raises something of its own.
- pxweb logs to the `pxweb` logger and sends a `pxweb-python` User-Agent by default; `sistat` passes its own.
- pxweb ships `pxweb.testing.FakePxWeb` so `sistat` tests don't keep a second copy of the fake server.
- Public API: `PxWebClient`, `TableInfo`, `Variable`, `TableMetadata`, `ServerLimits`, `Selection`, `fold`,
  `to_records` and the errors. `Session`, `Clock` and the query internals are not exported.
- The new repository starts with a fresh history; its first commit names the sistat commit it came from.
- Glossary terms for PxWeb concepts (Table, Variable, Value, Cell, Selection, Folded match, Record, Cell
  limit, Rate limit) move to pxweb's `GLOSSARY.md`; sistat's keeps only SiStat terms.

Order: clean the boundary inside this repo, extract and publish `pxweb-client` 0.1.0, then release
`sistat` 0.2.0 depending on it, with `src/sistat/pxweb/` deleted and no compatibility shim. sistat 0.1.0
was published shortly before this decision and is not known to have users, so its API is not preserved.

## Consequences

- Changes that touch both layers need two releases, and sistat must raise its upper bound to adopt a new
  pxweb minor version.
- Other PxWeb v1 servers can be used without installing anything SiStat-specific.
- sistat 0.2.0 breaks 0.1.0: `SiStatError` and `sistat.pxweb` are gone, and retry/rate-limit logs move from
  the `sistat` logger to `pxweb`.
