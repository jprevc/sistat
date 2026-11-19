"""SiStat-specific client built on the generic PxWeb v1 layer."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

import httpx

from .pxweb import PxWebClient, TableInfo, TableMetadata, to_records
from .pxweb import query as q

if TYPE_CHECKING:
    import pandas as pd

API_ROOT = "https://pxweb.stat.si/SiStatData/api/v1"
DATABASE = "Data"


def table_id(table: str) -> str:
    """Normalise ``"0156101S"`` / ``"0156101s.px"`` to ``"0156101S.px"``."""
    t = table.strip()
    if t.lower().endswith(".px"):
        t = t[:-3]
    return t.upper() + ".px"


def _fold(s: str) -> str:
    """Case- and accent-insensitive form, so 'brezposelnost' matches 'Brezposelnost' and 'cas' matches 'čas'."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(c))


class Client:
    """Client for the SiStat database of the Statistical Office of Slovenia (SURS).

    >>> c = Client(lang="en")
    >>> c.search("air temperature")
    >>> df = c.get("0156101S", {"METEOROLOGICAL STATION": "Ljubljana, Bežigrad"})
    """

    def __init__(
        self,
        lang: Literal["en", "sl"] = "en",
        *,
        api_root: str = API_ROOT,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.px = PxWebClient(api_root, DATABASE, lang, timeout=timeout, transport=transport)
        self._tables: list[TableInfo] | None = None
        self._meta: dict[str, TableMetadata] = {}

    @property
    def lang(self) -> str:
        return self.px.lang

    def close(self) -> None:
        self.px.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- discovery ----------------------------------------------------------

    def tables(self, refresh: bool = False) -> list[TableInfo]:
        """All tables in SiStat (one request, cached on the client)."""
        if self._tables is None or refresh:
            self._tables = [t for t in self.px.list() if t.type == "t"]
        return self._tables

    def search(self, text: str) -> list[TableInfo]:
        """Tables whose id or title contains every word of ``text`` (case- and accent-insensitive)."""
        words = _fold(text).split()
        return [t for t in self.tables() if all(w in _fold(f"{t.id} {t.text}") for w in words)]

    def metadata(self, table: str) -> TableMetadata:
        tid = table_id(table)
        if tid not in self._meta:
            self._meta[tid] = self.px.metadata(tid)
        return self._meta[tid]

    # -- data ---------------------------------------------------------------

    def get_records(self, table: str, selections: Mapping[str, q.Selection] | None = None, *, codes: bool = False) -> list[dict]:
        """Fetch data as a list of dicts, one per cell. See :meth:`get` for ``selections``."""
        tid = table_id(table)
        resolved = q.resolve(self.metadata(tid), selections)
        records: list[dict] = []
        for chunk in q.split(resolved, self.px.max_cells):
            data = self.px.query(tid, [r.to_json() for r in chunk])
            records.extend(to_records(data, codes=codes))
        return records

    def get(self, table: str, selections: Mapping[str, q.Selection] | None = None, *, codes: bool = False) -> pd.DataFrame:
        """Fetch data as a long-format pandas DataFrame.

        ``selections`` maps a variable (code or English/Slovenian label, case-insensitive) to:

        - a value code or label, or a list of them: ``["Ljubljana, Bežigrad", "11"]``
        - a glob pattern over codes or labels: ``"2020*"``; ``"*"`` means all
        - ``"top:N"``: the first N values in the table's order

        Variables you don't mention are fully selected. Large queries are split
        automatically to respect the server's cell limit.
        """
        try:
            import pandas as pd
        except ImportError as e:  # pragma: no cover
            raise ImportError("Client.get() needs pandas: pip install 'sistat[pandas]' (or use get_records())") from e
        return pd.DataFrame.from_records(self.get_records(table, selections, codes=codes))
