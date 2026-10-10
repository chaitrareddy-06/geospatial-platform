from dataclasses import dataclass, field, replace
from typing import Any

from shapely.geometry.base import BaseGeometry

from app.domain.enums.geometry_kind import GeometryKind


@dataclass(frozen=True)
class Feature:
    """One feature from an uploaded file, in a source-independent form."""

    index: int
    geometry: BaseGeometry | None
    properties: dict[str, Any] = field(default_factory=dict)
    skip_reason: str | None = None

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

    def with_skip_reason(self, reason: str) -> "Feature":
        """Return a copy marked as skipped (Feature itself is immutable)."""
        return replace(self, skip_reason=reason)