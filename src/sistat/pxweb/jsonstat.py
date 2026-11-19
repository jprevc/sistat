"""Minimal json-stat2 dataset -> records conversion."""

from __future__ import annotations

from itertools import product
from typing import Any


def _ordered_categories(dim: dict[str, Any]) -> list[str]:
    index = dim["category"].get("index")
    if index is None:  # single-category dimension may omit index
        return list(dim["category"]["label"])
    if isinstance(index, list):
        return list(index)
    return sorted(index, key=index.__getitem__)


def _cell_lookup(obj: Any, n: int) -> list[Any]:
    """json-stat allows value/status as a dense list, a sparse {index: v} dict, or (status) a single scalar."""
    if obj is None:
        return [None] * n
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        out: list[Any] = [None] * n
        for k, v in obj.items():
            out[int(k)] = v
        return out
    return [obj] * n


def to_records(dataset: dict[str, Any], *, codes: bool = False) -> list[dict[str, Any]]:
    """Flatten a json-stat2 dataset into one dict per cell (long/tidy format).

    Columns are the dimension labels holding value labels, plus ``value``.
    With ``codes=True`` a ``<label>_code`` column with the raw value code is added per dimension.
    A ``status`` column is added only when the dataset carries status symbols.
    """
    ids: list[str] = dataset["id"]
    sizes: list[int] = dataset["size"]
    n = 1
    for s in sizes:
        n *= s

    dims = []
    for dim_id in ids:
        dim = dataset["dimension"][dim_id]
        cats = _ordered_categories(dim)
        labels = dim["category"].get("label", {})
        dims.append((dim.get("label", dim_id), cats, labels))

    values = _cell_lookup(dataset.get("value"), n)
    statuses = _cell_lookup(dataset.get("status"), n) if "status" in dataset else None

    records = []
    for i, combo in enumerate(product(*(range(len(c)) for _, c, _ in dims))):
        rec: dict[str, Any] = {}
        for (label, cats, cat_labels), j in zip(dims, combo, strict=True):
            code = cats[j]
            rec[label] = cat_labels.get(code, code)
            if codes:
                rec[f"{label}_code"] = code
        rec["value"] = values[i]
        if statuses is not None:
            rec["status"] = statuses[i]
        records.append(rec)
    return records
