"""First line of defence for uploads: cheap checks before any parsing.

ZIP-specific checks (zip bomb, zip-slip, missing components) are added later.
"""

import hashlib
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.enums.file_kind import FileKind

_EXTENSION_TO_KIND = {
    ".zip": FileKind.ZIP_SHAPEFILE,
    ".kml": FileKind.KML,
}


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    kind: FileKind
    size_bytes: int
    sha256: str


def _safe_basename(filename: str | None) -> str:
    """Drop any directory part (handles both / and \\ separators)."""
    if not filename:
        return ""
    return filename.replace("\\", "/").split("/")[-1]


def validate_upload(
    filename: str | None,
    content: bytes,
    max_size_bytes: int | None = None,
) -> ValidatedUpload:
    limit = max_size_bytes if max_size_bytes is not None else settings.max_upload_size_bytes
    name = _safe_basename(filename)
    size = len(content)

    if size == 0:
        raise EmptyFileError(details={"filename": name})

    dot = name.rfind(".")
    extension = name[dot:].lower() if dot != -1 else ""
    kind = _EXTENSION_TO_KIND.get(extension)
    if kind is None:
        raise UnsupportedFileTypeError(
            details={"filename": name, "extension": extension, "allowed": sorted(_EXTENSION_TO_KIND)}
        )

    if size > limit:
        raise FileTooLargeError(details={"size_bytes": size, "limit_bytes": limit})

    return ValidatedUpload(
        filename=name,
        kind=kind,
        size_bytes=size,
        sha256=hashlib.sha256(content).hexdigest(),
    )