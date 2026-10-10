"""Application exceptions.

Pure Python: no FastAPI imports. Services raise these; the API layer
translates them into HTTP responses (done in a later part).
"""

from typing import Any


class AppError(Exception):
    """Base class for all expected, handled errors."""

    status_code: int = 500
    error_code: str = "internal_error"
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


# ---- File validation errors ----
class FileValidationError(AppError):
    status_code = 400
    error_code = "file_validation_failed"
    default_message = "The uploaded file is not valid."


class EmptyFileError(FileValidationError):
    error_code = "empty_file"
    default_message = "The uploaded file is empty."


class UnsupportedFileTypeError(FileValidationError):
    status_code = 415
    error_code = "unsupported_file_type"
    default_message = "Only .zip (Shapefile) and .kml files are supported."


class FileTooLargeError(FileValidationError):
    status_code = 413
    error_code = "file_too_large"
    default_message = "The uploaded file exceeds the maximum allowed size."


class CorruptArchiveError(FileValidationError):
    status_code = 422
    error_code = "corrupt_archive"
    default_message = "The ZIP archive is corrupted or unreadable."


class UnsafeArchiveError(FileValidationError):
    status_code = 422
    error_code = "unsafe_archive"
    default_message = "The archive was rejected for safety reasons."


class MissingShapefileComponentError(FileValidationError):
    status_code = 422
    error_code = "missing_shapefile_component"
    default_message = "The Shapefile is missing a required component."


class CorruptKMLError(FileValidationError):
    status_code = 422
    error_code = "corrupt_kml"
    default_message = "The KML file is malformed or unreadable."

    
class CorruptShapefileError(FileValidationError):
    status_code = 422
    error_code = "corrupt_shapefile"
    default_message = "The Shapefile could not be read."


# ---- Processing errors ----
class CRSResolutionError(AppError):
    status_code = 422
    error_code = "crs_resolution_failed"
    default_message = "Could not determine a usable coordinate reference system."


class GeometryProcessingError(AppError):
    status_code = 422
    error_code = "geometry_processing_failed"
    default_message = "A geometry could not be processed."


# ---- Resource errors ----
class ResourceNotFoundError(AppError):
    status_code = 404
    error_code = "not_found"
    default_message = "The requested resource was not found."


class DuplicateFileError(AppError):
    status_code = 409
    error_code = "duplicate_file"
    default_message = "A file with identical content has already been uploaded."