"""Generic PxWeb API v1 client.

Knows nothing about SiStat specifically: give it any PxWeb v1 base URL
(``https://<host>/<app>/api/v1/<lang>/<database>``).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx

from . import query as q
from .jsonstat import to_records
from .models import ServerLimits, TableInfo, TableMetadata
from .session import Session

USER_AGENT = "pxweb-python"


class PxWebClient:
    def __init__(
        self,
        api_root: str,
        database: str,
        lang: str,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        user_agent: str = USER_AGENT,
    ):
        """``api_root`` is the part before the language, e.g. ``https://host/App/api/v1``.

        Applications built on this client should pass their own ``user_agent`` so server operators can tell them apart.
        """
        self.api_root = api_root.rstrip("/")
        self.database = database
        self.lang = lang
        self.retries = retries
        self._http = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": user_agent})
        self._session = Session(self._http, f"{self.api_root}/{lang}/?config", retries=retries)
        self._meta: dict[str, TableMetadata] = {}

    # -- plumbing -----------------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"{self.api_root}/{self.lang}/{self.database}"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PxWebClient:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def _url(self, path: str = "") -> str:
        path = "/".join(quote(p) for p in path.strip("/").split("/") if p)
        return f"{self.base_url}/{path}" if path else self.base_url

    # -- API ----------------------------------------------------------------

    @property
    def limits(self) -> ServerLimits:
        """The server's cell limit and rate limit, read from ``?config`` on first use (defaults if unavailable)."""
        return self._session.limits

    def _post(self, table: str, query: list[dict[str, Any]]) -> dict[str, Any]:
        """POST a raw PxWeb query (list of ``{"code", "selection"}``) and return the json-stat2 dataset."""
        body = {"query": query, "response": {"format": "json-stat2"}}
        dataset: dict[str, Any] = self._session.send("POST", self._url(table), json=body).json()
        return dataset

    def tables(self, path: str = "") -> list[TableInfo]:
        """List tables (and folders) at ``path`` within the database."""
        return [TableInfo.from_json(d) for d in self._session.send("GET", self._url(path)).json()]

    def metadata(self, table: str) -> TableMetadata:
        """The table's variables and values (fetched once, cached on the client)."""
        if table not in self._meta:
            self._meta[table] = TableMetadata.from_json(self._session.send("GET", self._url(table)).json())
        return self._meta[table]

    def get_records(self, table: str, selections: Mapping[str, q.Selection] | None = None, *, codes: bool = False) -> list[dict[str, Any]]:
        """Fetch data as a list of records, one per cell.

        ``selections`` maps a variable (code or label, case-insensitive) to a value code or label,
        a list of them, a glob pattern (``"20*"``, ``"*"``), or ``"top:N"``. Variables not mentioned
        are fully selected. Queries over the server's cell limit are split and the results merged.
        """
        resolved = q.resolve(self.metadata(table), selections)
        records: list[dict[str, Any]] = []
        for chunk in q.split(resolved, self.limits.cell_limit):
            records.extend(to_records(self._post(table, [r.to_json() for r in chunk]), codes=codes))
        return records
