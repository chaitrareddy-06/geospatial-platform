"""Safely extract Shapefile components from a ZIP into a temporary folder.

Files are written under names we choose (shapefile_<n>.<ext>), so archive
entry names never influence where anything lands on disk.
"""

import io
import posixpath
import tempfile
import zipfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import CorruptArchiveError, UnsafeArchiveError
from app.services.zip_validation import inspect_shapefile_zip

EXTRACTABLE_EXTENSIONS = (".shp", ".shx", ".dbf", ".prj", ".cpg")
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class ExtractedShapefile:
    source_stem: str  # original path inside the archive, without extension
    shp_path: Path  # the extracted .shp (siblings sit next to it)
    has_prj: bool


def _extract(
    content: bytes,
    stems: tuple[str, ...],
    dest: Path,
    limit: int,
) -> list[ExtractedShapefile]:
    wanted = {stem.lower(): index for index, stem in enumerate(stems)}

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        selected: dict[tuple[int, str], zipfile.ZipInfo] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            stem, ext = posixpath.splitext(info.filename.replace("\\", "/"))
            ext = ext.lower()
            index = wanted.get(stem.lower())
            if index is None or ext not in EXTRACTABLE_EXTENSIONS:
                continue
            if (index, ext) in selected:
                raise UnsafeArchiveError(
                    "The archive contains duplicate entries for the same file.",
                    details={"entry": info.filename},
                )
            selected[(index, ext)] = info

        written = 0
        for (index, ext), info in sorted(selected.items()):
            target = dest / f"shapefile_{index}{ext}"
            with archive.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(CHUNK_SIZE):
                    written += len(chunk)
                    if written > limit:
                        raise UnsafeArchiveError(
                            "The archive expanded beyond the allowed size while extracting.",
                            details={"limit_bytes": limit},
                        )
                    out.write(chunk)

    return [
        ExtractedShapefile(
            source_stem=stem,
            shp_path=dest / f"shapefile_{index}.shp",
            has_prj=(index, ".prj") in selected,
        )
        for index, stem in enumerate(stems)
    ]


@contextmanager
def extract_shapefiles(
    content: bytes,
    max_extract_bytes: int | None = None,
) -> Iterator[list[ExtractedShapefile]]:
    """Inspect, then extract. The temp folder is deleted when the block ends."""
    limit = max_extract_bytes if max_extract_bytes is not None else settings.max_uncompressed_size_bytes
    inspection = inspect_shapefile_zip(content)

    with tempfile.TemporaryDirectory(prefix="shp_extract_") as tmp:
        try:
            results = _extract(content, inspection.shapefile_stems, Path(tmp), limit)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as exc:
            raise CorruptArchiveError(details={"reason": str(exc)}) from exc
        yield results