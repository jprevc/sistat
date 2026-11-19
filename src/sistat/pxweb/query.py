"""Turn friendly selections into PxWeb v1 query JSON."""

from __future__ import annotations

import fnmatch
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from ..errors import QueryError
from .models import TableMetadata, Variable

T = TypeVar("T")

Selection = str | int | Iterable[str | int]


@dataclass
class Resolved:
    """A selection for one variable: explicit value codes, or the first N via ``top``."""

    variable: Variable
    codes: list[str] | None = None
    top: int | None = None

    @property
    def count(self) -> int:
        return min(self.top, len(self.variable.values)) if self.top is not None else len(self.codes or ())

    def to_json(self) -> dict:
        if self.top is not None:
            return {"code": self.variable.code, "selection": {"filter": "top", "values": [str(self.top)]}}
        return {"code": self.variable.code, "selection": {"filter": "item", "values": list(self.codes or ())}}


def fold(s: str) -> str:
    """Case- and accent-insensitive form (also stripped), so ' cas' matches 'Čas'."""
    return "".join(c for c in unicodedata.normalize("NFKD", _casefold(s)) if not unicodedata.combining(c))


def _casefold(s: str) -> str:
    return s.casefold().strip()


def _matches(key: str, candidates: Iterable[tuple[T, str, str]]) -> list[T]:
    """Items whose code or label matches ``key``, from the first tier that has any.

    Tiers, in order: code ignoring case, label ignoring case, code folded, label folded.
    """
    triples = list(candidates)
    for norm in (_casefold, fold):
        k = norm(key)
        for hits in ([i for i, code, _ in triples if norm(code) == k], [i for i, _, label in triples if norm(label) == k]):
            if hits:
                return list(dict.fromkeys(hits))
    return []


def _ambiguous(key: str, where: str, labels: Iterable[str]) -> QueryError:
    return QueryError(f"{key!r} is ambiguous in {where}: matches {', '.join(repr(t) for t in labels)}")


def find_variable(meta: TableMetadata, key: str) -> Variable:
    """Match a variable by code or label (see ``_matches`` and "Folded match" in GLOSSARY.md)."""
    hits = _matches(key, ((v, v.code, v.text) for v in meta.variables))
    if len(hits) > 1:
        raise _ambiguous(key, repr(meta.title), (v.text for v in hits))
    if hits:
        return hits[0]
    choices = ", ".join(repr(v.text) for v in meta.variables)
    raise QueryError(f"Unknown variable {key!r}. Available: {choices}")


def _resolve_values(var: Variable, wanted: Iterable[str]) -> list[str]:
    pairs = list(zip(var.values, var.value_texts, strict=True))
    out: list[str] = []
    for w in wanted:
        w = str(w)
        if any(ch in w for ch in "*?["):
            pat = fold(w)
            hits = [c for c, t in pairs if any(fnmatch.fnmatchcase(fold(s), pat) for s in (c, t))]
            if not hits:
                raise QueryError(f"Pattern {w!r} matches no value of {var.text!r}")
            out.extend(hits)
            continue
        hits = _matches(w, ((c, c, t) for c, t in pairs))
        if not hits:
            sample = ", ".join(repr(t) for t in var.value_texts[:10])
            more = f" … ({len(var.values)} total)" if len(var.values) > 10 else ""
            raise QueryError(f"{w!r} is not a value of {var.text!r}. Values: {sample}{more}")
        if len(hits) > 1:
            labels = var.labels()
            raise _ambiguous(w, repr(var.text), (labels[c] for c in hits))
        out.append(hits[0])
    return list(dict.fromkeys(out))  # dedupe, keep order


def resolve(meta: TableMetadata, selections: Mapping[str, Selection] | None = None) -> list[Resolved]:
    """Resolve selections against metadata. Variables not mentioned select all their values.

    A selection is a value code or label, a list of them, a glob pattern (``"20*"``),
    ``"*"`` for everything, or ``"top:N"`` for the first N values in table order.
    """
    selections = dict(selections or {})
    chosen: dict[str, Resolved] = {}
    for key, sel in selections.items():
        var = find_variable(meta, key)
        if isinstance(sel, str) and sel.lower().startswith("top:"):
            try:
                n = int(sel[4:])
            except ValueError:
                raise QueryError(f"Bad top selection {sel!r}; use 'top:<N>'") from None
            chosen[var.code] = Resolved(var, top=n)
            continue
        items = [sel] if isinstance(sel, (str, int)) else list(sel)
        if not items:
            raise QueryError(f"Empty selection for {var.text!r}")
        chosen[var.code] = Resolved(var, codes=_resolve_values(var, items))
    # Explicitly select everything else: otherwise PxWeb silently drops ("eliminates") those variables.
    return [chosen.get(v.code) or Resolved(v, codes=list(v.values)) for v in meta.variables]


def cell_count(resolved: list[Resolved]) -> int:
    n = 1
    for r in resolved:
        n *= r.count
    return n


def split(resolved: list[Resolved], max_cells: int) -> list[list[Resolved]]:
    """Split a query into chunks of at most ``max_cells`` cells by chunking the largest item dimensions."""
    if cell_count(resolved) <= max_cells:
        return [resolved]
    candidates = [i for i, r in enumerate(resolved) if r.codes is not None and len(r.codes) > 1]
    if not candidates:
        raise QueryError(f"Query of {cell_count(resolved)} cells exceeds the server limit of {max_cells} and cannot be split")
    i = max(candidates, key=lambda j: len(resolved[j].codes))
    codes = resolved[i].codes
    rest = cell_count(resolved) // len(codes)
    per_chunk = max(1, max_cells // rest)
    chunks = []
    for start in range(0, len(codes), per_chunk):
        part = list(resolved)
        part[i] = Resolved(resolved[i].variable, codes=codes[start : start + per_chunk])
        chunks.extend(split(part, max_cells))
    return chunks
