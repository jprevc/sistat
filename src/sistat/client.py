"""SiStat-specific client built on the generic PxWeb v1 layer."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import version
from types import TracebackType
from typing import Any, Literal

import httpx
from pxweb import PxWebClient, Selection, TableInfo, TableMetadata, fold

API_ROOT = "https://pxweb.stat.si/SiStatData/api/v1"
DATABASE = "Data"
USER_AGENT = f"sistat-python/{version('sistat')}"


def table_id(table: str) -> str:
    """Normalise ``"0156101S"`` / ``"0156101s.px"`` to ``"0156101S.px"``."""
    t = table.strip()
    if t.lower().endswith(".px"):
        t = t[:-3]
    return t.upper() + ".px"


class Client:
    """Client for the SiStat database of the Statistical Office of Slovenia (SURS).

    >>> c = Client(lang="en")
    >>> c.search("air temperature")
    >>> records = c.get_records("0156101S", {"METEOROLOGICAL STATION": "Ljubljana, Bežigrad"})
    """

    def __init__(
        self,
        lang: Literal["en", "sl"] = "en",
        *,
        api_root: str = API_ROOT,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.px = PxWebClient(api_root, DATABASE, lang, timeout=timeout, transport=transport, user_agent=USER_AGENT)
        self._tables: list[TableInfo] | None = None

    @property
    def lang(self) -> str:
        return self.px.lang

    def close(self) -> None:
        self.px.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    # -- discovery ----------------------------------------------------------

    def tables(self, refresh: bool = False) -> list[TableInfo]:
        """All tables in SiStat (one request, cached on the client)."""
        if self._tables is None or refresh:
            self._tables = [t for t in self.px.tables() if t.type == "t"]
        return self._tables

    def search(self, text: str) -> list[TableInfo]:
        """Tables whose id or title contains every word of ``text`` (case- and accent-insensitive)."""
        words = fold(text).split()
        return [t for t in self.tables() if all(w in fold(f"{t.id} {t.text}") for w in words)]

    def metadata(self, table: str) -> TableMetadata:
        return self.px.metadata(table_id(table))

    # -- data ---------------------------------------------------------------

    def get_records(self, table: str, selections: Mapping[str, Selection] | None = None, *, codes: bool = False) -> list[dict[str, Any]]:
        """Fetch data as a list of dicts, one per cell (long format).

        ``selections`` maps a variable (code or English/Slovenian label, case-insensitive) to:

        - a value code or label, or a list of them: ``["Ljubljana, Bežigrad", "11"]``
        - a glob pattern over codes or labels: ``"2020*"``; ``"*"`` means all
        - ``"top:N"``: the first N values in the table's order

        Variables you don't mention are fully selected. Large queries are split
        automatically to respect the server's cell limit.

        For a DataFrame, pass the result to ``pandas.DataFrame(...)`` or ``polars.DataFrame(...)``.
        """
        return self.px.get_records(table_id(table), selections, codes=codes)
