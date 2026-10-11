"""In-memory feature-result store (thread-safe, lost on restart)."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from app.domain.entities.feature_page import FeaturePage, LayeredFeature
from app.domain.entities.feature_result import ProcessedFeature


class InMemoryFeatureResultRepository:
    def __init__(self) -> None:
        self._items: dict[str, list[LayeredFeature]] = {}
        self._lock = threading.Lock()

    def add_layer(
        self, file_id: str, layer: str, features: Sequence[ProcessedFeature]
    ) -> None:
        with self._lock:
            bucket = self._items.setdefault(file_id, [])
            bucket.extend(LayeredFeature(layer, feature) for feature in features)

    def list_page(
        self,
        file_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        status: str | None = None,
    ) -> FeaturePage:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be >= 0 and limit must be >= 1")
        with self._lock:
            items = list(self._items.get(file_id, ()))
        if status is not None:
            items = [item for item in items if item.feature.status == status]
        return FeaturePage(
            items=tuple(items[offset : offset + limit]),
            total=len(items),
            offset=offset,
            limit=limit,
        )