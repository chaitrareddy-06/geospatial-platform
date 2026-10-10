import hashlib

import pytest

from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.enums.file_kind import FileKind
from app.services.file_validation import validate_upload


@pytest.mark.parametrize(
    ("filename", "kind"),
    [
        ("survey.kml", FileKind.KML),
        ("survey.KML", FileKind.KML),
        ("data.ZIP", FileKind.ZIP_SHAPEFILE),
    ],
)
def test_accepts_supported_extensions(filename, kind):
    result = validate_upload(filename, b"abc")
    assert result.kind == kind
    assert result.size_bytes == 3


def test_sha256_matches_hashlib():
    result = validate_upload("a.kml", b"hello")
    assert result.sha256 == hashlib.sha256(b"hello").hexdigest()


def test_hash_differs_for_different_content():
    a = validate_upload("a.kml", b"one")
    b = validate_upload("a.kml", b"two")
    assert a.sha256 != b.sha256


def test_empty_file_rejected():
    with pytest.raises(EmptyFileError):
        validate_upload("a.kml", b"")


@pytest.mark.parametrize("filename", ["a.txt", "a.shp", "noext", "", "a.zip.exe"])
def test_unsupported_extension_rejected(filename):
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(filename, b"abc")


def test_oversize_rejected_with_details():
    with pytest.raises(FileTooLargeError) as info:
        validate_upload("a.kml", b"x" * 11, max_size_bytes=10)
    assert info.value.details == {"size_bytes": 11, "limit_bytes": 10}


def test_file_exactly_at_limit_is_accepted():
    result = validate_upload("a.kml", b"x" * 10, max_size_bytes=10)
    assert result.size_bytes == 10


def test_directory_part_of_filename_is_stripped():
    result = validate_upload("..\\..\\evil/path/survey.kml", b"abc")
    assert result.filename == "survey.kml"