"""Generic PxWeb API v1 client.

Knows nothing about SiStat specifically: give it any PxWeb v1 base URL
(``https://<host>/<app>/api/v1/<lang>/<database>``).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from urllib.parse import quote

import httpx

from ..errors import APIError
from .models import TableInfo, TableMetadata

DEFAULT_LIMITS = {"maxValues": 100_000, "maxCalls": 30, "timeWindow": 10}
RETRY_STATUS = {429, 502, 503, 504}


class RateLimiter:
    """Sliding-window limiter: at most ``max_calls`` per ``window`` seconds."""

    def __init__(self, max_calls: int, window: float):
        self.max_calls = max_calls
        self.window = window
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= self.window:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                time.sleep(self.window - (now - self._calls[0]))
                self._calls.popleft()
            self._calls.append(time.monotonic())


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
    ):
        """``api_root`` is the part before the language, e.g. ``https://host/App/api/v1``."""
        self.api_root = api_root.rstrip("/")
        self.database = database
        self.lang = lang
        self.retries = retries
        self._http = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": "sistat-python"})
        self._limits: dict | None = None
        self._limiter: RateLimiter | None = None

    # -- plumbing -----------------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"{self.api_root}/{self.lang}/{self.database}"

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        if self._limiter is None and not url.endswith("?config"):
            limits = self.limits
            # keep a small safety margin under the server's limit
            self._limiter = RateLimiter(max(1, int(limits["maxCalls"] * 0.9)), float(limits["timeWindow"]))
        for attempt in range(self.retries + 1):
            if self._limiter:
                self._limiter.acquire()
            try:
                resp = self._http.request(method, url, **kw)
            except httpx.TransportError as e:
                if attempt == self.retries:
                    raise APIError(f"{method} {url} failed: {e}") from e
            else:
                if resp.status_code not in RETRY_STATUS or attempt == self.retries:
                    break
            time.sleep(2**attempt)
        if resp.is_error:
            body = resp.text.strip()[:200] or resp.reason_phrase
            raise APIError(f"{method} {url} -> {resp.status_code}: {body}", resp.status_code)
        return resp

    def _url(self, path: str = "") -> str:
        path = "/".join(quote(p) for p in path.strip("/").split("/") if p)
        return f"{self.base_url}/{path}" if path else self.base_url

    # -- API ----------------------------------------------------------------

    @property
    def limits(self) -> dict:
        """Server limits (``maxValues``/``maxCells``, ``maxCalls``, ``timeWindow``) from ``?config``."""
        if self._limits is None:
            try:
                cfg = self._request("GET", f"{self.api_root}/{self.lang}/?config").json()
            except (APIError, ValueError):
                cfg = {}
            self._limits = {**DEFAULT_LIMITS, **cfg}
        return self._limits

    @property
    def max_cells(self) -> int:
        lim = self.limits
        return int(lim.get("maxCells") or lim["maxValues"])

    def list(self, path: str = "") -> list[TableInfo]:
        """List tables (and folders) at ``path`` within the database."""
        return [TableInfo.from_json(d) for d in self._request("GET", self._url(path)).json()]

    def metadata(self, table: str) -> TableMetadata:
        return TableMetadata.from_json(self._request("GET", self._url(table)).json())

    def query(self, table: str, query: list[dict], fmt: str = "json-stat2") -> dict:
        """POST a raw PxWeb query (list of ``{"code", "selection"}``) and return the parsed JSON."""
        body = {"query": query, "response": {"format": fmt}}
        return self._request("POST", self._url(table), json=body).json()
