import json

import httpx
import pytest

from sistat import APIError, Client, QueryError
from sistat.pxweb import PxWebClient, ServerLimits

from .conftest import FakePxWeb

TABLE = "0156101S.px"
STATION = "METEOROLOGICAL STATION"


def bodies(fake):
    return [json.loads(r.content) for r in fake.requests if r.method == "POST"]


def test_labels_and_top_and_unmentioned_variables_selected_explicitly(px, fake):
    recs = px.get_records(TABLE, {"meteorological station": ["Ljubljana, Bežigrad", "11"], "PERIOD, YEAR": "top:2"})

    (body,) = bodies(fake)
    sel = {q["code"]: q["selection"] for q in body["query"]}
    assert sel["METEOROLOŠKA POSTAJA"] == {"filter": "item", "values": ["10", "11"]}
    assert sel["OBDOBJE, LETO"] == {"filter": "top", "values": ["2"]}
    # MEASURE has elimination=True; omitting it would silently drop it, so it must be sent.
    assert sel["MERITVE"]["values"] == [str(i) for i in range(13)]
    assert body["response"] == {"format": "json-stat2"}

    assert len(recs) == 2 * 2 * 13
    (row,) = [r for r in recs if r[STATION] == "Maribor, Tabor" and r["PERIOD, YEAR"] == "1981-1990" and r["MEASURE"] == "January"]
    assert row["value"] == -0.9


def test_codes_columns(px):
    recs = px.get_records(TABLE, {STATION: "10", "PERIOD, YEAR": "1981-1990", "MEASURE": "January"}, codes=True)
    assert recs == [
        {
            STATION: "Ljubljana, Bežigrad",
            f"{STATION}_code": "10",
            "PERIOD, YEAR": "1981-1990",
            "PERIOD, YEAR_code": "1981-1990",
            "MEASURE": "January",
            "MEASURE_code": "1",
            "value": -1.1,
        }
    ]


def test_glob_pattern(px, fake):
    px.get_records(TABLE, {STATION: ["Ljubljana*", "Maribor*"], "PERIOD, YEAR": "19*", "MEASURE": "0"})
    sel = {q["code"]: q["selection"]["values"] for q in bodies(fake)[0]["query"]}
    assert sel["METEOROLOŠKA POSTAJA"] == ["10", "11"]
    assert sel["OBDOBJE, LETO"] == ["1981-1990", "1991-2000"]


def test_unknown_variable_lists_choices(px):
    with pytest.raises(QueryError, match="Available: 'METEOROLOGICAL STATION'"):
        px.get_records(TABLE, {"REGION": "x"})


def test_unknown_value_lists_choices(px):
    with pytest.raises(QueryError, match="'Ljubljana' is not a value of 'METEOROLOGICAL STATION'.*Bilje"):
        px.get_records(TABLE, {STATION: "Ljubljana"})


def test_large_query_is_split_and_merged():
    fake = FakePxWeb(max_cells=30)
    with PxWebClient("https://example.test/api/v1", "Data", "en", transport=httpx.MockTransport(fake)) as px:
        recs = px.get_records(TABLE, {STATION: ["10", "11"], "PERIOD, YEAR": ["1981-1990", "1991-2000"]})
    assert len(recs) == 52
    assert len(bodies(fake)) == 2  # 52 cells, limit 30 -> split on a 2-value dimension
    assert all(len(q["selection"]["values"]) <= 13 for b in bodies(fake) for q in b["query"])


def test_metadata_is_fetched_once(px, fake):
    px.get_records(TABLE, {STATION: "10", "PERIOD, YEAR": "top:1"})
    px.get_records(TABLE, {STATION: "11", "PERIOD, YEAR": "top:1"})
    px.metadata(TABLE)
    assert sum(r.method == "GET" and r.url.path.endswith(TABLE) for r in fake.requests) == 1


def test_api_error(px):
    with pytest.raises(APIError) as e:
        px.metadata("NOPE.px")
    assert e.value.status_code == 400


def test_limits_are_typed(px):
    assert px.limits == ServerLimits(cell_limit=50_000_000, max_calls=500, time_window=10.0)


def test_constructing_a_client_makes_no_request(fake):
    with PxWebClient("https://example.test/api/v1", "Data", "en", transport=httpx.MockTransport(fake)):
        pass
    with Client(transport=httpx.MockTransport(fake)):
        pass
    assert fake.requests == []
