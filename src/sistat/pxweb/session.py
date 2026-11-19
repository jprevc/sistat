"""Request policy for one PxWeb connection: server config, rate limit, retry/backoff and error mapping."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Protocol

import httpx

from ..errors import APIError
from .models import DEFAULT_LIMITS, ServerLimits

log = logging.getLogger("sistat")

RETRY_STATUS = {429, 502, 503, 504}
MAX_RETRY_AFTER = 60.0
CONFIG_TIMEOUT = 5.0
# Keep a safety margin under the server's rate limit.
RATE_LIMIT_MARGIN = 0.9


class Clock(Protocol):
    """Time source for rate limiting and backoff; tests substitute a fake."""

    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class _SystemClock:
    """The real clock: ``time.monotonic`` and ``time.sleep``."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


SYSTEM_CLOCK: Clock = _SystemClock()


class Session:
    """Request policy for one PxWeb connection.

    Reads the server's limits from ``?config`` on first use, keeps requests under the rate limit,
    retries transient failures with backoff, and maps error responses to :class:`APIError`.
    """

    def __init__(self, http: httpx.Client, config_url: str, *, retries: int, clock: Clock = SYSTEM_CLOCK):
        self._http = http
        self._config_url = config_url
        self._retries = retries
        self._clock = clock
        self._lock = threading.Lock()
        self._limits: ServerLimits | None = None
        self._calls: deque[float] = deque()

    @property
    def limits(self) -> ServerLimits:
        """The server's limits, fetched from ``?config`` on first use."""
        if self._limits is not None:  # set once, never changes: no need to wait behind a sleeping caller
            return self._limits
        with self._lock:
            return self._ensure_limits()

    def _ensure_limits(self) -> ServerLimits:
        if self._limits is None:
            # One short attempt, no retries: the defaults are safe, and a broken config
            # endpoint must not delay the real request.
            try:
                resp = self._http.get(self._config_url, timeout=CONFIG_TIMEOUT)
                resp.raise_for_status()
                self._limits = ServerLimits.from_config(resp.json())
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as e:
                log.warning("Could not read server limits from %s (%s); using defaults %s", self._config_url, e, DEFAULT_LIMITS)
                self._limits = DEFAULT_LIMITS
        return self._limits

    def _acquire(self) -> None:
        """Wait until another call fits in the sliding rate-limit window, then record it.

        Holds the lock while sleeping, so threads sharing a session take turns.
        """
        with self._lock:
            limits = self._ensure_limits()
            max_calls = max(1, int(limits.max_calls * RATE_LIMIT_MARGIN))
            now = self._clock.monotonic()
            while self._calls and now - self._calls[0] >= limits.time_window:
                self._calls.popleft()
            if len(self._calls) >= max_calls:
                self._clock.sleep(limits.time_window - (now - self._calls[0]))
                self._calls.popleft()
            self._calls.append(self._clock.monotonic())

    def send(self, method: str, url: str, **kw) -> httpx.Response:
        """Send a request under the server's rate limit, retrying transient failures; raise :class:`APIError` on error."""
        attempt = 0
        while True:
            self._acquire()
            try:
                resp = self._http.request(method, url, **kw)
            except httpx.TransportError as e:
                if attempt == self._retries:
                    raise APIError(f"{method} {url} failed: {e}") from e
                self._clock.sleep(_retry_delay(None, attempt))
            else:
                if resp.status_code not in RETRY_STATUS or attempt == self._retries:
                    return _raise_for_error(method, url, resp)
                self._clock.sleep(_retry_delay(resp, attempt))
            attempt += 1


def _raise_for_error(method: str, url: str, resp: httpx.Response) -> httpx.Response:
    """Return ``resp``, or raise :class:`APIError` if it is an error response."""
    if resp.is_error:
        body = resp.text.strip()[:200] or resp.reason_phrase
        raise APIError(f"{method} {url} -> {resp.status_code}: {body}", resp.status_code)
    return resp


def _retry_delay(resp: httpx.Response | None, attempt: int) -> float:
    """``Retry-After`` in whole seconds (capped) if the server sent one, otherwise exponential backoff."""
    header = resp.headers.get("Retry-After", "").strip() if resp is not None else ""
    if header.isascii() and header.isdigit():
        return min(float(header), MAX_RETRY_AFTER)
    return float(2**attempt)
