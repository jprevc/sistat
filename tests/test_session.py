"""Request policy: server config bootstrap, rate limit, retry/backoff and error mapping."""

import logging
import threading
import time

import httpx
import pytest

from sistat.pxweb import APIError, ServerLimits
from sistat.pxweb.models import DEFAULT_LIMITS
from sistat.pxweb.session import CONFIG_TIMEOUT, Session

CONFIG_URL = "https://example.test/api/v1/en/?config"
URL = "https://example.test/api/v1/en/Data"
CONFIG = {"maxValues": 1000, "maxCalls": 10, "timeWindow": 10}


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Server:
    """Answers ``?config`` with ``config`` and other requests from a queue of responses (then 200s)."""

    def __init__(self, *responses, config=CONFIG):
        self.responses = list(responses)
        self.config = config
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.query == b"config":
            if isinstance(self.config, Exception):
                raise self.config
            if isinstance(self.config, httpx.Response):
                return self.config
            return httpx.Response(200, json=self.config)
        r = self.responses.pop(0) if self.responses else httpx.Response(200, json=[])
        if isinstance(r, Exception):
            raise r
        return r

    @property
    def data_requests(self):
        return [r for r in self.requests if r.url.query != b"config"]

    @property
    def config_requests(self):
        return [r for r in self.requests if r.url.query == b"config"]


def make_session(server: Server, clock: FakeClock, retries: int = 3) -> Session:
    return Session(httpx.Client(transport=httpx.MockTransport(server)), CONFIG_URL, retries=retries, clock=clock)


@pytest.fixture
def clock():
    return FakeClock()


def test_retryable_status_is_retried_then_succeeds(clock):
    server = Server(httpx.Response(503))
    resp = make_session(server, clock).send("GET", URL)
    assert resp.status_code == 200
    assert len(server.data_requests) == 2
    assert clock.sleeps == [1]


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(429), httpx.Response(502), httpx.Response(503), httpx.Response(504), httpx.ConnectError("refused")],
    ids=["429", "502", "503", "504", "transport"],
)
def test_each_retryable_failure_is_retried(clock, failure):
    server = Server(failure)
    assert make_session(server, clock).send("POST", URL, json={}).status_code == 200
    assert len(server.data_requests) == 2


def test_exhausted_retries_raise_api_error_with_status_and_back_off_exponentially(clock):
    server = Server(*[httpx.Response(503, text="busy")] * 4)
    with pytest.raises(APIError, match=r"GET .*Data -> 503: busy") as e:
        make_session(server, clock, retries=3).send("GET", URL)
    assert e.value.status_code == 503
    assert len(server.data_requests) == 4
    assert clock.sleeps == [1, 2, 4]


def test_exhausted_retries_on_transport_error_raise_api_error(clock):
    server = Server(*[httpx.ConnectError("refused")] * 4)
    with pytest.raises(APIError, match="failed: refused") as e:
        make_session(server, clock, retries=3).send("GET", URL)
    assert e.value.status_code is None


def test_non_retryable_error_is_not_retried(clock):
    server = Server(httpx.Response(500, text="bad query"))
    with pytest.raises(APIError, match="-> 500: bad query"):
        make_session(server, clock).send("GET", URL)
    assert len(server.data_requests) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize(
    "header, expected_sleeps",
    [
        ("3", [3, 3, 3]),
        ("600", [60, 60, 60]),
        ("Wed, 21 Oct 2026 07:28:00 GMT", [1, 2, 4]),
        ("7.5", [1, 2, 4]),
        ("\u00b2".encode("latin-1"), [1, 2, 4]),  # a Unicode digit ("²") is not a number of seconds
    ],
    ids=["seconds", "capped", "http-date-falls-back", "non-integer-falls-back", "unicode-digit-falls-back"],
)
def test_retry_after_whole_seconds_is_honoured_and_capped(clock, header, expected_sleeps):
    server = Server(*[httpx.Response(429, headers={"Retry-After": header})] * 3)
    make_session(server, clock).send("GET", URL)
    assert clock.sleeps == expected_sleeps


def test_limits_come_from_server_config_with_max_cells_preferred(clock):
    server = Server(config={"maxValues": 1000, "maxCells": 5000, "maxCalls": 20, "timeWindow": 5})
    assert make_session(server, clock).limits == ServerLimits(cell_limit=5000, max_calls=20, time_window=5.0)


def test_cell_limit_falls_back_to_max_values(clock):
    assert make_session(Server(), clock).limits.cell_limit == 1000


def test_config_is_fetched_lazily_and_once(clock):
    server = Server()
    session = make_session(server, clock)
    assert server.requests == []
    for _ in range(5):
        session.send("GET", URL)
    assert session.limits.max_calls == 10
    assert len(server.config_requests) == 1
    assert server.requests[0].url.query == b"config"


@pytest.mark.parametrize(
    "config",
    [httpx.Response(503), httpx.ConnectError("refused"), httpx.Response(200, text="<html>not json</html>")],
    ids=["5xx", "transport", "invalid-json"],
)
def test_failed_config_falls_back_to_defaults_at_once_and_warns(clock, caplog, config):
    server = Server(config=config)
    with caplog.at_level(logging.WARNING, logger="pxweb"):
        session = make_session(server, clock)
        session.send("GET", URL)
        session.send("GET", URL)
    assert session.limits == DEFAULT_LIMITS
    assert len(server.config_requests) == 1
    assert clock.sleeps == []
    assert [r.levelname for r in caplog.records if r.name.startswith("pxweb")] == ["WARNING"]


def test_successful_config_logs_nothing(clock, caplog):
    with caplog.at_level(logging.DEBUG, logger="pxweb"):
        make_session(Server(), clock).send("GET", URL)
    assert not [r for r in caplog.records if r.name.startswith("pxweb")]


def test_config_request_uses_short_timeout(clock):
    server = Server()
    make_session(server, clock).send("GET", URL)
    (cfg,) = server.config_requests
    assert cfg.extensions["timeout"]["read"] == CONFIG_TIMEOUT


def test_rate_limit_allows_nine_tenths_of_max_calls_per_window_without_waiting(clock):
    session = make_session(Server(), clock)  # maxCalls 10 per 10 s -> 9 allowed
    for _ in range(9):
        session.send("GET", URL)
    assert clock.sleeps == []


def test_rate_limit_waits_for_the_rest_of_the_window_when_full(clock):
    session = make_session(Server(), clock)
    session.send("GET", URL)  # t=0
    clock.now = 4.0
    for _ in range(8):
        session.send("GET", URL)  # window now holds 9 calls
    session.send("GET", URL)
    assert clock.sleeps == [6.0]  # until the t=0 call leaves the 10 s window


def test_rate_limit_does_not_wait_once_the_window_has_passed(clock):
    session = make_session(Server(), clock)
    for _ in range(9):
        session.send("GET", URL)
    clock.now = 10.0
    for _ in range(9):
        session.send("GET", URL)
    assert clock.sleeps == []


def test_rate_limit_allows_at_least_one_call(clock):
    session = make_session(Server(config={"maxCalls": 1, "timeWindow": 10}), clock)
    session.send("GET", URL)
    session.send("GET", URL)
    assert clock.sleeps == [10.0]


def test_concurrent_first_calls_fetch_config_once(clock):
    class SlowConfig(Server):
        def __call__(self, request):
            if request.url.query == b"config":
                time.sleep(0.05)  # widen the race window
            return super().__call__(request)

    server = SlowConfig(config={**CONFIG, "maxCalls": 1000})
    session = make_session(server, clock)
    threads = [threading.Thread(target=session.send, args=("GET", URL)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(server.config_requests) == 1
    assert len(server.data_requests) == 8


def test_zero_from_server_config_is_kept(clock):
    assert make_session(Server(config={**CONFIG, "maxCalls": 0}), clock).limits.max_calls == 0
