import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pxweb.testing import FakePxWeb

from sistat import Client

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = "0156101S.px"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_fake(**kwargs: Any) -> FakePxWeb:
    """Recorded SiStat responses (stations 10,11 x first 2 periods x 13 measures) served as database ``Data``."""
    return FakePxWeb(
        "Data",
        tables=load("tables.json"),
        metadata={TABLE: load("meta_0156101S.json")},
        data={TABLE: load("data_0156101S.json")},
        **kwargs,
    )


@pytest.fixture
def fake():
    return make_fake()


@pytest.fixture
def client(fake):
    with Client(transport=httpx.MockTransport(fake)) as c:
        yield c
