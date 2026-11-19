"""Data models for PxWeb v1 responses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableInfo:
    """One entry of a database listing."""

    id: str
    text: str
    type: str = "t"
    updated: str | None = None

    @classmethod
    def from_json(cls, d: dict) -> TableInfo:
        return cls(id=d["id"], text=d.get("text", ""), type=d.get("type", "t"), updated=d.get("updated"))


@dataclass(frozen=True)
class Variable:
    """A table dimension: a code plus its values and their human-readable labels."""

    code: str
    text: str
    values: tuple[str, ...]
    value_texts: tuple[str, ...]
    elimination: bool = False
    time: bool = False

    @classmethod
    def from_json(cls, d: dict) -> Variable:
        values = tuple(d.get("values", ()))
        return cls(
            code=d["code"],
            text=d.get("text", d["code"]),
            values=values,
            value_texts=tuple(d.get("valueTexts", values)),
            elimination=bool(d.get("elimination", False)),
            time=bool(d.get("time", False)),
        )

    def labels(self) -> dict[str, str]:
        """Mapping of value code -> value label."""
        return dict(zip(self.values, self.value_texts, strict=True))


@dataclass(frozen=True)
class TableMetadata:
    title: str
    variables: tuple[Variable, ...] = field(default_factory=tuple)

    @classmethod
    def from_json(cls, d: dict) -> TableMetadata:
        return cls(title=d.get("title", ""), variables=tuple(Variable.from_json(v) for v in d.get("variables", ())))

    @property
    def size(self) -> int:
        """Number of cells in the full table."""
        n = 1
        for v in self.variables:
            n *= len(v.values)
        return n


@dataclass(frozen=True)
class ServerLimits:
    """What the server allows: the most cells per request (the cell limit) and at most
    ``max_calls`` requests per ``time_window`` seconds (the rate limit)."""

    cell_limit: int
    max_calls: int
    time_window: float

    @classmethod
    def from_config(cls, cfg: dict) -> ServerLimits:
        """Parse a PxWeb ``?config`` response; keys it lacks fall back to :data:`DEFAULT_LIMITS`."""
        d = DEFAULT_LIMITS
        return cls(
            cell_limit=int(cfg.get("maxCells") or cfg.get("maxValues") or d.cell_limit),
            max_calls=int(cfg.get("maxCalls", d.max_calls)),
            time_window=float(cfg.get("timeWindow", d.time_window)),
        )


DEFAULT_LIMITS = ServerLimits(cell_limit=100_000, max_calls=30, time_window=10.0)
