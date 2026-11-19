"""An in-memory PxWeb v1 server for tests, used with :class:`httpx.MockTransport`.

>>> fake = FakePxWeb("Data", tables=[...], metadata={"T.px": meta}, data={"T.px": jsonstat})
>>> client = PxWebClient("https://example.test/api/v1", "Data", "en", transport=httpx.MockTransport(fake))
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from itertools import product
from typing import Any

import httpx


class FakePxWeb:
    """Serves recorded responses and records every request in :attr:`requests`.

    ``tables`` is the database's table listing, ``metadata`` maps a table id to its metadata response, and
    ``data`` maps a table id to a full json-stat2 response. A data query is answered by slicing that response
    to the query's ``item`` and ``top`` selections; Variables left out of the query are returned in full.
    """

    def __init__(
        self,
        database: str,
        tables: list[dict[str, Any]],
        metadata: Mapping[str, dict[str, Any]],
        data: Mapping[str, dict[str, Any]],
        *,
        max_cells: int = 50_000_000,
        max_calls: int = 500,
        time_window: int = 10,
    ):
        self.database = database
        self.tables = tables
        self.metadata = dict(metadata)
        self.data = dict(data)
        self.requests: list[httpx.Request] = []
        self.config = {"maxValues": max_cells, "maxCells": max_cells, "maxCalls": max_calls, "timeWindow": time_window}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.query == b"config":
            return httpx.Response(200, json=self.config)
        last = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        if last == self.database and request.method == "GET":
            return httpx.Response(200, json=self.tables)
        if last in self.metadata:
            if request.method == "GET":
                return httpx.Response(200, json=self.metadata[last])
            if last in self.data:
                return httpx.Response(200, json=slice_jsonstat(self.data[last], json.loads(request.content)))
        return httpx.Response(400, text="Bad Request")


def slice_jsonstat(full: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Answer the PxWeb query ``body`` from the complete json-stat2 dataset ``full``."""
    ids, sizes = full["id"], full["size"]
    cats = [sorted(full["dimension"][d]["category"]["index"], key=full["dimension"][d]["category"]["index"].get) for d in ids]
    sel: dict[int, list[str]] = {}
    for item in body["query"]:
        s = item["selection"]
        d = ids.index(item["code"])
        sel[d] = cats[d][: int(s["values"][0])] if s["filter"] == "top" else s["values"]
    keep = [sel.get(d, cats[d]) for d in range(len(ids))]
    strides = [1] * len(ids)
    for d in range(len(ids) - 2, -1, -1):
        strides[d] = strides[d + 1] * sizes[d + 1]

    values = [full["value"][sum(cats[d].index(c) * strides[d] for d, c in enumerate(combo))] for combo in product(*keep)]
    out = copy.deepcopy(full)
    out["size"] = [len(k) for k in keep]
    for d, dim in enumerate(ids):
        cat = out["dimension"][dim]["category"]
        cat["index"] = {c: i for i, c in enumerate(keep[d])}
        cat["label"] = {c: cat["label"][c] for c in keep[d]}
    out["value"] = values
    return out
