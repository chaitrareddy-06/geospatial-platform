"""Per-feature result types.

These describe what happened to one feature (measured, skipped or failed)
and what was measured. They are plain frozen dataclasses with no framework
imports, so a repository can store and return them without depending on a
service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.domain.enums.geometry_kind import GeometryKind

LengthMethod = Literal["projected", "geodesic"]


@dataclass(frozen=True)
class Measurement:
    kind: GeometryKind
    area_m2: float | None = None
    length_m: float | None = None
    part_count: int | None = None  # for Multi* and collections
    unsupported_parts: tuple[str, ...] = ()  # geometry types we could not measure


@dataclass(frozen=True)
class CrossCheck:
    """Projected vs geodesic comparison for one feature.

    ``*_diff_pct`` = (projected - geodesic) / geodesic * 100.
    A value is None when the feature has no such quantity.
    """

    geodesic_area_m2: float | None
    geodesic_length_m: float | None
    area_diff_pct: float | None
    length_diff_pct: float | None


@dataclass(frozen=True)
class ProcessedFeature:
    """One feature's outcome: what it was, what happened, what was measured."""

    index: int
    kind: GeometryKind
    status: str  # "measured" | "skipped" | "failed"
    reason: str | None  # human-readable sentence
    reason_code: str | None  # stable machine code; None when measured
    repaired: bool
    properties: dict[str, Any]
    measurement: Measurement | None
    cross_check: CrossCheck | None
    length_method: LengthMethod | None