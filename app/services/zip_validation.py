"""Inspect a Shapefile ZIP in memory, without extracting it.

Pure Python. Raises the typed exceptions from app.core.exceptions.
"""

import io
import posixpath
import zipfile
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import (
    CorruptArchiveError,
    MissingShapefileComponentError,
    UnsafeArchiveError,
)

MAX_ENTRIES = 1000
_REQUIRED_COMPANIONS = (".shx", ".dbf")


@dataclass(frozen=True)
class ZipInspection:
    shapefile_stems: tuple[str, ...]  # archive paths of each .shp, without extension
    total_uncompressed_bytes: int
    warnings: tuple[str, ...]


def _normalize(name: str) -> str:
    return name.replace("\\", "/")


def _is_unsafe_path(name: str) -> bool:
    n = _normalize(name)
    if n.startswith("/"):
        return True
    if len(n) >= 2 and n[1] == ":":  # Windows drive letter, e.g. C:/x
        return True
    return ".." in n.split("/")


def _is_junk(name: str) -> bool:
    parts = _normalize(name).split("/")
    return "__MACOSX" in parts or parts[-1].startswith("._")


def inspect_shapefile_zip(
    content: bytes,
    max_uncompressed_bytes: int | None = None,
    max_ratio: int | None = None,
    max_entries: int = MAX_ENTRIES,
) -> ZipInspection:
    size_limit = (
        max_uncompressed_bytes
        if max_uncompressed_bytes is not None
        else settings.max_uncompressed_size_bytes
    )
    ratio_limit = max_ratio if max_ratio is not None else settings.max_compression_ratio

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise CorruptArchiveError(details={"reason": str(exc)}) from exc

    with archive:
        infos = archive.infolist()

        if len(infos) > max_entries:
            raise UnsafeArchiveError(
                "The archive contains too many files.",
                details={"entries": len(infos), "limit": max_entries},
            )

        # Safety checks on every entry, directories included.
        for info in infos:
            if _is_unsafe_path(info.filename):
                raise UnsafeArchiveError(
                    "The archive contains an unsafe file path.",
                    details={"entry": info.filename},
                )
            if info.flag_bits & 0x1:
                raise UnsafeArchiveError(
                    "Password-protected archives are not supported.",
                    details={"entry": info.filename},
                )

        total = sum(info.file_size for info in infos)
        if total > size_limit:
            raise UnsafeArchiveError(
                "The archive expands to more than the allowed size.",
                details={"uncompressed_bytes": total, "limit_bytes": size_limit},
            )
        ratio = total / len(content)
        if ratio > ratio_limit:
            raise UnsafeArchiveError(
                "The archive compression ratio is suspiciously high (possible zip bomb).",
                details={"ratio": round(ratio, 1), "limit": ratio_limit},
            )

        # Group real files by stem (case-insensitive) to find shapefile components.
        groups: dict[str, dict[str, object]] = {}
        for info in infos:
            if info.is_dir() or _is_junk(info.filename):
                continue
            stem, ext = posixpath.splitext(_normalize(info.filename))
            group = groups.setdefault(stem.lower(), {"stem": stem, "exts": set()})
            group["exts"].add(ext.lower())  # type: ignore[union-attr]

    shapefiles = [g for g in groups.values() if ".shp" in g["exts"]]  # type: ignore[operator]
    if not shapefiles:
        raise MissingShapefileComponentError(
            "The archive does not contain a .shp file.",
            details={"missing": [".shp"]},
        )

    stems: list[str] = []
    warnings: list[str] = []
    for group in sorted(shapefiles, key=lambda g: str(g["stem"])):
        stem = str(group["stem"])
        exts: set[str] = group["exts"]  # type: ignore[assignment]
        missing = [e for e in _REQUIRED_COMPANIONS if e not in exts]
        if missing:
            raise MissingShapefileComponentError(
                details={"shapefile": stem, "missing": missing},
            )
        if ".prj" not in exts:
            warnings.append(f"{stem}: no .prj file, so the CRS is unknown")
        stems.append(stem)

    return ZipInspection(
        shapefile_stems=tuple(stems),
        total_uncompressed_bytes=total,
        warnings=tuple(warnings),
    )