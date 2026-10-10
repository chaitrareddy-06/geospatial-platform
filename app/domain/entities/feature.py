from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from shapely.geometry.base import BaseGeometry

from app.domain.enums.geometry_kind import GeometryKind


@dataclass(frozen=True)
class Feature:
    index: int
    geometry: BaseGeometry | None
    properties: dict[str, Any] = field(default_factory=dict)
    skip_reason: str | None = None
    repaired: bool = False

    @property
    def kind(self) -> GeometryKind:
        if self.geometry is None:
            return GeometryKind.NULL
        return GeometryKind.from_geom_type(self.geometry.geom_type)

    @property
    def is_empty(self) -> bool:
        return self.geometry is not None and self.geometry.is_empty

    @property
    def is_skipped(self) -> bool:
        return self.skip_reason is not None

    def with_skip_reason(self, reason: str) -> Feature:
        return replace(self, skip_reason=reason)

    def with_geometry(self, geometry: BaseGeometry, repaired: bool = True) -> Feature:
        return replace(self, geometry=geometry, repaired=repaired)