import json

import httpx
import pytest

from sistat import APIError, Client, QueryError, table_id

from .conftest import FakeSiStat

STATION = "METEOROLOGICAL STATION"


def bodies(fake):
    return [json.loads(r.content) for r in fake.requests if r.method == "POST"]


def test_table_id_normalisation():
    assert table_id("0156101S") == "0156101S.px"
    assert table_id("0156101s.PX") == "0156101S.px"


def test_search_is_case_and_accent_insensitive(client):
    assert [t.id for t in client.search("AIR temperatures")] == ["0156101S.px"]
    assert len(client.search("unemployed persons")) == 3
    assert client.search("nothing like this") == []


def test_tables_are_fetched_once(client, fake):
    client.search("air")
    client.search("unemployed")
    assert sum(r.url.path.endswith("/Data") for r in fake.requests) == 1


def test_metadata(client):
    meta = client.metadata("0156101S")
    assert [v.text for v in meta.variables] == [STATION, "PERIOD, YEAR", "MEASURE"]
    assert meta.variables[0].code == "METEOROLOŠKA POSTAJA"
    assert meta.variables[2].elimination


def test_get_by_labels_selects_all_other_variables_explicitly(client, fake):
    df = client.get("0156101S", {"meteorological station": ["Ljubljana, Bežigrad", "11"], "PERIOD, YEAR": "top:2"})

    (body,) = bodies(fake)
    sel = {q["code"]: q["selection"] for q in body["query"]}
    assert sel["METEOROLOŠKA POSTAJA"] == {"filter": "item", "values": ["10", "11"]}
    assert sel["OBDOBJE, LETO"] == {"filter": "top", "values": ["2"]}
    # MEASURE has elimination=True; omitting it would silently drop it, so it must be sent.
    assert sel["MERITVE"]["values"] == [str(i) for i in range(13)]
    assert body["response"] == {"format": "json-stat2"}

    assert list(df.columns) == [STATION, "PERIOD, YEAR", "MEASURE", "value"]
    assert len(df) == 2 * 2 * 13
    row = df[(df[STATION] == "Maribor, Tabor") & (df["PERIOD, YEAR"] == "1981-1990") & (df["MEASURE"] == "January")]
    assert row["value"].item() == -0.9


def test_codes_columns(client):
    recs = client.get_records("0156101S", {STATION: "10", "PERIOD, YEAR": "1981-1990", "MEASURE": "January"}, codes=True)
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


def test_glob_pattern(client, fake):
    client.get_records("0156101S", {STATION: ["Ljubljana*", "Maribor*"], "PERIOD, YEAR": "19*", "MEASURE": "0"})
    sel = {q["code"]: q["selection"]["values"] for q in bodies(fake)[0]["query"]}
    assert sel["METEOROLOŠKA POSTAJA"] == ["10", "11"]
    assert sel["OBDOBJE, LETO"] == ["1981-1990", "1991-2000"]


def test_unknown_variable_lists_choices(client):
    with pytest.raises(QueryError, match="Available: 'METEOROLOGICAL STATION'"):
        client.get_records("0156101S", {"REGION": "x"})


def test_unknown_value_lists_choices(client):
    with pytest.raises(QueryError, match="'Ljubljana' is not a value of 'METEOROLOGICAL STATION'.*Bilje"):
        client.get_records("0156101S", {STATION: "Ljubljana"})


def test_large_query_is_split():
    fake = FakeSiStat(max_cells=30)
    with Client(transport=httpx.MockTransport(fake)) as c:
        recs = c.get_records("0156101S", {STATION: ["10", "11"], "PERIOD, YEAR": ["1981-1990", "1991-2000"]})
    assert len(recs) == 52
    assert len(bodies(fake)) == 2  # 52 cells, limit 30 -> split on a 2-value dimension
    assert all(len(q["selection"]["values"]) <= 13 for b in bodies(fake) for q in b["query"])


def test_api_error(client):
    with pytest.raises(APIError) as e:
        client.metadata("NOPE")
    assert e.value.status_code == 400


@pytest.mark.live
def test_live_roundtrip():
    with Client() as c:
        assert len(c.tables()) > 1000
        df = c.get("0156101S", {STATION: "Ljubljana, Bežigrad", "PERIOD, YEAR": "2014", "MEASURE": "January"})
        assert len(df) == 1 and df["value"].notna().all()
