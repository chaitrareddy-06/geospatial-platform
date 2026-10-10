import io
import zipfile

import pytest

from app.core.exceptions import (
    CorruptArchiveError,
    MissingShapefileComponentError,
    UnsafeArchiveError,
)
from app.services.zip_validation import inspect_shapefile_zip


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


FULL = {"data.shp": b"s", "data.shx": b"x", "data.dbf": b"d", "data.prj": b"p"}


def test_complete_shapefile_is_accepted():
    result = inspect_shapefile_zip(make_zip(FULL))
    assert result.shapefile_stems == ("data",)
    assert result.warnings == ()


def test_missing_prj_is_a_warning_not_an_error():
    files = {k: v for k, v in FULL.items() if k != "data.prj"}
    result = inspect_shapefile_zip(make_zip(files))
    assert result.shapefile_stems == ("data",)
    assert len(result.warnings) == 1
    assert ".prj" in result.warnings[0]


def test_nested_folder_and_uppercase_extensions():
    files = {
        "folder/Parcels.SHP": b"s",
        "folder/Parcels.SHX": b"x",
        "folder/Parcels.DBF": b"d",
    }
    result = inspect_shapefile_zip(make_zip(files))
    assert result.shapefile_stems == ("folder/Parcels",)


def test_macos_junk_files_are_ignored():
    files = {**FULL, "__MACOSX/._data.shp": b"junk", "__MACOSX/._data.dbf": b"junk"}
    result = inspect_shapefile_zip(make_zip(files))
    assert result.shapefile_stems == ("data",)


@pytest.mark.parametrize("dropped", ["data.shx", "data.dbf"])
def test_missing_required_component(dropped):
    files = {k: v for k, v in FULL.items() if k != dropped}
    with pytest.raises(MissingShapefileComponentError) as info:
        inspect_shapefile_zip(make_zip(files))
    assert info.value.details["missing"] == [f".{dropped.split('.')[1]}"]


def test_zip_without_shp_is_rejected():
    with pytest.raises(MissingShapefileComponentError) as info:
        inspect_shapefile_zip(make_zip({"data.dbf": b"d", "data.shx": b"x"}))
    assert info.value.details["missing"] == [".shp"]


def test_not_a_zip_is_corrupt():
    with pytest.raises(CorruptArchiveError):
        inspect_shapefile_zip(b"this is not a zip file")


def test_truncated_zip_is_corrupt():
    good = make_zip(FULL)
    with pytest.raises(CorruptArchiveError):
        inspect_shapefile_zip(good[:-10])


@pytest.mark.parametrize(
    "bad_name",
    ["../evil.txt", "a/../../evil.txt", "/abs.txt", "C:/x.txt", "..\\evil.txt"],
)
def test_zip_slip_paths_are_rejected(bad_name):
    with pytest.raises(UnsafeArchiveError):
        inspect_shapefile_zip(make_zip({**FULL, bad_name: b"x"}))


def test_zip_bomb_ratio_is_rejected():
    bomb = make_zip({**FULL, "big.bin": b"\x00" * 1_000_000})
    with pytest.raises(UnsafeArchiveError) as info:
        inspect_shapefile_zip(bomb)
    assert "ratio" in info.value.details


def test_declared_size_over_limit_is_rejected():
    with pytest.raises(UnsafeArchiveError) as info:
        inspect_shapefile_zip(make_zip({**FULL, "x.bin": b"y" * 100}), max_uncompressed_bytes=50)
    assert "uncompressed_bytes" in info.value.details


def test_too_many_entries_is_rejected():
    with pytest.raises(UnsafeArchiveError):
        inspect_shapefile_zip(make_zip(FULL), max_entries=2)