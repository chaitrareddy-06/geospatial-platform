import pytest

from app.core.exceptions import (
    AppError,
    CorruptArchiveError,
    CorruptKMLError,
    CRSResolutionError,
    DuplicateFileError,
    EmptyFileError,
    FileTooLargeError,
    FileValidationError,
    GeometryProcessingError,
    MissingShapefileComponentError,
    ResourceNotFoundError,
    UnsafeArchiveError,
    UnsupportedFileTypeError,
)


def test_default_message_and_empty_details():
    err = EmptyFileError()
    assert err.message == "The uploaded file is empty."
    assert err.details == {}
    assert str(err) == err.message


def test_custom_message_and_details_override_defaults():
    err = FileTooLargeError("Too big", details={"limit_mb": 50})
    assert err.message == "Too big"
    assert err.details == {"limit_mb": 50}
    assert err.status_code == 413
    assert err.error_code == "file_too_large"


def test_details_are_not_shared_between_instances():
    a = AppError()
    b = AppError()
    a.details["x"] = 1
    assert b.details == {}


@pytest.mark.parametrize(
    ("exc_class", "status", "code"),
    [
        (FileValidationError, 400, "file_validation_failed"),
        (EmptyFileError, 400, "empty_file"),
        (UnsupportedFileTypeError, 415, "unsupported_file_type"),
        (FileTooLargeError, 413, "file_too_large"),
        (CorruptArchiveError, 422, "corrupt_archive"),
        (UnsafeArchiveError, 422, "unsafe_archive"),
        (MissingShapefileComponentError, 422, "missing_shapefile_component"),
        (CorruptKMLError, 422, "corrupt_kml"),
        (CRSResolutionError, 422, "crs_resolution_failed"),
        (GeometryProcessingError, 422, "geometry_processing_failed"),
        (ResourceNotFoundError, 404, "not_found"),
        (DuplicateFileError, 409, "duplicate_file"),
    ],
)
def test_status_and_error_code(exc_class, status, code):
    err = exc_class()
    assert err.status_code == status
    assert err.error_code == code


def test_file_errors_share_a_common_base():
    for exc_class in (
        EmptyFileError,
        UnsupportedFileTypeError,
        FileTooLargeError,
        CorruptArchiveError,
        UnsafeArchiveError,
        MissingShapefileComponentError,
        CorruptKMLError,
    ):
        assert issubclass(exc_class, FileValidationError)
        assert issubclass(exc_class, AppError)


def test_unique_error_codes():
    classes = [
        AppError, FileValidationError, EmptyFileError, UnsupportedFileTypeError,
        FileTooLargeError, CorruptArchiveError, UnsafeArchiveError,
        MissingShapefileComponentError, CorruptKMLError, CRSResolutionError,
        GeometryProcessingError, ResourceNotFoundError, DuplicateFileError,
    ]
    codes = [c.error_code for c in classes]
    assert len(codes) == len(set(codes))