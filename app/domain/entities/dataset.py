from dataclasses import dataclass

from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind


@dataclass(frozen=True)
class ParsedDataset:
    """Everything a parser extracted from one upload (or one layer of it)."""

    source_name: str
    source_kind: FileKind
    features: tuple[Feature, ...]
    crs_text: str | None  # EPSG code or WKT as found in the file; None if missing
    warnings: tuple[str, ...] = ()

    @property
    def feature_count(self) -> int:
        return len(self.features)

    @property
    def skipped_count(self) -> int:
        return sum(1 for f in self.features if f.is_skipped)