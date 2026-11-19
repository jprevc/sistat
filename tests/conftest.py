import json
from pathlib import Path

import httpx
import pytest

from sistat import Client

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeSiStat:
    """In-memory stand-in for the SiStat API, recording every request."""

    def __init__(self, max_cells: int = 50_000_000):
        self.requests: list[httpx.Request] = []
        self.config = {"maxValues": max_cells, "maxCells": max_cells, "maxCalls": 500, "timeWindow": 10}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.query == b"config":
            return httpx.Response(200, json=self.config)
        if path.endswith("/Data"):
            return httpx.Response(200, json=load("tables.json"))
        if path.endswith("/0156101S.px"):
            if request.method == "GET":
                return httpx.Response(200, json=load("meta_0156101S.json"))
            return httpx.Response(200, json=self._data(json.loads(request.content)))
        return httpx.Response(400, text="Bad Request")

    def _data(self, body: dict) -> dict:
        """Answer a query by slicing the real fixture (stations 10,11 x first 2 periods x 13 measures)."""
        full = load("data_0156101S.json")
        ids, sizes = full["id"], full["size"]
        cats = [sorted(full["dimension"][d]["category"]["index"], key=full["dimension"][d]["category"]["index"].get) for d in ids]
        sel = {}
        for item in body["query"]:
            s = item["selection"]
            d = ids.index(item["code"])
            sel[d] = cats[d][: int(s["values"][0])] if s["filter"] == "top" else s["values"]
        keep = [sel.get(d, cats[d]) for d in range(len(ids))]
        strides = [1] * len(ids)
        for d in range(len(ids) - 2, -1, -1):
            strides[d] = strides[d + 1] * sizes[d + 1]
        from itertools import product

        values = [full["value"][sum(cats[d].index(c) * strides[d] for d, c in enumerate(combo))] for combo in product(*keep)]
        out = json.loads(json.dumps(full))
        out["size"] = [len(k) for k in keep]
        for d, dim in enumerate(ids):
            cat = out["dimension"][dim]["category"]
            cat["index"] = {c: i for i, c in enumerate(keep[d])}
            cat["label"] = {c: cat["label"][c] for c in keep[d]}
        out["value"] = values
        return out


@pytest.fixture
def fake():
    return FakeSiStat()


@pytest.fixture
def client(fake):
    with Client(transport=httpx.MockTransport(fake)) as c:
        yield c
