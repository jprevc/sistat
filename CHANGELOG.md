# Changelog

## 0.2.0

The generic PxWeb v1 client now lives in its own package, [`pxweb-client`](https://github.com/jprevc/pxweb),
which sistat depends on ([ADR 0001](docs/adr/0001-extract-pxweb-package.md)).

### Breaking

- `sistat.pxweb` is removed. Install `pxweb-client` and `import pxweb` instead.
- `SiStatError` is removed. Catch `sistat.PxWebError` (the same class as `pxweb.PxWebError`).
  `sistat.APIError` and `sistat.QueryError` are now pxweb's classes, with the same behaviour.
- The warning about unreadable server limits is logged to the `pxweb` logger instead of `sistat`.
- `PxWebClient.list()` is renamed to `tables()`.

### Changed

- Requests send a `sistat-python/<version>` User-Agent.

## 0.1.0

First release.
