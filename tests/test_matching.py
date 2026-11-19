"""Folded match rules for Selections, on synthetic metadata (see GLOSSARY.md)."""

import pytest

from sistat import QueryError
from sistat.pxweb.models import TableMetadata, Variable
from sistat.pxweb.query import resolve


def meta(*labels: str, codes: tuple[str, ...] | None = None) -> TableMetadata:
    codes = codes or tuple(str(i) for i in range(len(labels)))
    return TableMetadata(title="t", variables=(Variable(code="KRAJ", text="PLACE", values=codes, value_texts=labels),))


def picked(m: TableMetadata, sel) -> list[str]:
    (r,) = resolve(m, {"PLACE": sel})
    return r.codes


def test_exact_match_beats_folded_match():
    m = meta("Čas", "Cas")
    assert picked(m, "čas") == ["0"]
    assert picked(m, "cas") == ["1"]


def test_value_code_beats_another_values_label():
    assert picked(meta("2", "x", codes=("1", "2")), "2") == ["2"]


def test_folded_collision_is_ambiguous():
    with pytest.raises(QueryError, match=r"ambiguous.*'Čaš'.*'Cāš'"):
        picked(meta("Čaš", "Cāš"), "cas")


def test_labels_differing_only_by_case_are_ambiguous():
    with pytest.raises(QueryError, match="ambiguous"):
        picked(meta("Total", "TOTAL"), "total")


def test_glob_with_folded_collision_selects_all():
    assert picked(meta("Čaš", "Cāš", "Dan"), "cas*") == ["0", "1"]


def test_variables_colliding_when_folded_are_ambiguous():
    v = [Variable(code=c, text=c, values=("1",), value_texts=("1",)) for c in ("ŠOLA", "SOLA")]
    m = TableMetadata(title="t", variables=tuple(v))
    assert resolve(m, {"šola": "1"})[0].codes == ["1"]  # exact match wins
    with pytest.raises(QueryError, match=r"'sóla' is ambiguous.*'ŠOLA', 'SOLA'"):
        resolve(m, {"sóla": "1"})
