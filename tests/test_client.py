import pytest

from sistat import Client, table_id

STATION = "METEOROLOGICAL STATION"


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


def test_metadata_accepts_unnormalised_ids(client, fake):
    meta = client.metadata("0156101s")
    assert client.metadata("0156101S.PX") is meta
    assert [v.text for v in meta.variables] == [STATION, "PERIOD, YEAR", "MEASURE"]
    assert meta.variables[0].code == "METEOROLOŠKA POSTAJA"
    assert meta.variables[2].elimination
    assert sum(r.url.path.endswith("/0156101S.px") for r in fake.requests) == 1


def test_get_records_returns_long_records(client):
    recs = client.get_records("0156101s", {STATION: ["Ljubljana, Bežigrad", "11"], "PERIOD, YEAR": "top:2"})
    assert list(recs[0]) == [STATION, "PERIOD, YEAR", "MEASURE", "value"]
    assert len(recs) == 2 * 2 * 13
    [row] = [r for r in recs if r[STATION] == "Maribor, Tabor" and r["PERIOD, YEAR"] == "1981-1990" and r["MEASURE"] == "January"]
    assert row["value"] == -0.9


@pytest.mark.live
def test_live_roundtrip():
    with Client() as c:
        assert len(c.tables()) > 1000
        [rec] = c.get_records("0156101S", {STATION: "Ljubljana, Bežigrad", "PERIOD, YEAR": "2014", "MEASURE": "January"})
        assert rec["value"] is not None
