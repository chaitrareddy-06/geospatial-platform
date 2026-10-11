"""A page of stored per-feature results, as returned by a repository."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.feature_result import ProcessedFeature


@dataclass(frozen=True)
class LayeredFeature:
    """A processed feature together with the layer (dataset) it came from."""

    layer: str
    feature: ProcessedFeature


@dataclass(frozen=True)
class FeaturePage:
    """One page of results. ``total`` counts all matches, not just this page."""

    items: tuple[LayeredFeature, ...]
    total: int
    offset: int
    limit: int