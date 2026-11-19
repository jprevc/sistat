from sistat.pxweb import to_records


def ds(**kw):
    base = {
        "id": ["A", "B"],
        "size": [2, 2],
        "dimension": {
            "A": {"label": "Alpha", "category": {"index": {"a1": 0, "a2": 1}, "label": {"a1": "A one", "a2": "A two"}}},
            "B": {"label": "Beta", "category": {"index": ["b1", "b2"], "label": {"b1": "B one", "b2": "B two"}}},
        },
        "value": [1, 2, 3, 4],
    }
    return base | kw


def test_row_major_order():
    recs = to_records(ds())
    assert [(r["Alpha"], r["Beta"], r["value"]) for r in recs] == [
        ("A one", "B one", 1),
        ("A one", "B two", 2),
        ("A two", "B one", 3),
        ("A two", "B two", 4),
    ]
    assert "status" not in recs[0]


def test_sparse_values_and_status():
    recs = to_records(ds(value={"0": 1, "3": 4}, status={"1": "..."}))
    assert [r["value"] for r in recs] == [1, None, None, 4]
    assert [r["status"] for r in recs] == [None, "...", None, None]


def test_index_order_is_respected():
    d = ds()
    d["dimension"]["A"]["category"]["index"] = {"a2": 0, "a1": 1}
    assert [r["Alpha"] for r in to_records(d)][::2] == ["A two", "A one"]
