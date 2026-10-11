"""Storage interface for per-feature results.

Like FileRepository, this is a Protocol: services depend on it, and a
PostgreSQL implementation can replace the in-memory one later.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.entities.feature_page import FeaturePage
from app.domain.entities.feature_result import ProcessedFeature


class FeatureResultRepository(Protocol):
    def add_layer(
        self, file_id: str, layer: str, features: Sequence[ProcessedFeature]
    ) -> None:
        """Store all features of one layer of a file, keeping their order."""
        ...

    def list_page(
        self,
        file_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        status: str | None = None,
    ) -> FeaturePage:
        """Return one page, optionally filtered by status.

        An unknown file id gives an empty page. Raises ValueError if
        offset < 0 or limit < 1.
        """
        ...