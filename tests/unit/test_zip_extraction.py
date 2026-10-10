import io
import zipfile

import pytest

from app.core.exceptions import CorruptArchiveError, UnsafeArchiveError
from app.services.zip_extraction import extract_shapefiles


def make_zip(files: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


FULL = {"data.shp": b"s", "data.shx": b"x", "data.dbf": b"d", "data.prj": b"p"}


def test_extracts_components_with_safe_flat_names():
    with extract_shapefiles(make_zip(FULL)) as results:
        assert len(results) == 1
        shp = results[0].shp_path
        assert shp.name == "shapefile_0.shp"
        assert shp.read_bytes() == b"s"
        assert (shp.parent / "shapefile_0.dbf").read_bytes() == b"d"
        assert results[0].source_stem == "data"


def test_has_prj_flag():
    with extract_shapefiles(make_zip(FULL)) as results:
        assert results[0].has_prj is True
    no_prj = {k: v for k, v in FULL.items() if k != "data.prj"}
    with extract_shapefiles(make_zip(no_prj)) as results:
        assert results[0].has_prj is False


def test_only_shapefile_components_are_extracted():
    files = {**FULL, "data.txt": b"t", "readme.md": b"m", "data.exe": b"e"}
    with extract_shapefiles(make_zip(files)) as results:
        names = sorted(p.name for p in results[0].shp_path.parent.iterdir())
    assert names == ["shapefile_0.dbf", "shapefile_0.prj", "shapefile_0.shp", "shapefile_0.shx"]


def test_nested_folder_and_uppercase_extensions():
    files = {
        "folder/Parcels.SHP": b"s",
        "folder/Parcels.SHX": b"x",
        "folder/Parcels.DBF": b"d",
    }
    with extract_shapefiles(make_zip(files)) as results:
        assert results[0].source_stem == "folder/Parcels"
        assert results[0].shp_path.exists()
        assert (results[0].shp_path.parent / "shapefile_0.dbf").exists()


def test_multiple_shapefiles_get_distinct_paths():
    files = {
        "a.shp": b"1", "a.shx": b"1", "a.dbf": b"1",
        "b.shp": b"2", "b.shx": b"2", "b.dbf": b"2",
    }
    with extract_shapefiles(make_zip(files)) as results:
        assert [r.source_stem for r in results] == ["a", "b"]
        assert results[0].shp_path != results[1].shp_path
        assert results[0].shp_path.read_bytes() == b"1"
        assert results[1].shp_path.read_bytes() == b"2"


def test_temp_folder_removed_after_use():
    with extract_shapefiles(make_zip(FULL)) as results:
        folder = results[0].shp_path.parent
        assert folder.exists()
    assert not folder.exists()


def test_temp_folder_removed_even_if_caller_fails():
    captured = {}
    with pytest.raises(RuntimeError):
        with extract_shapefiles(make_zip(FULL)) as results:
            captured["folder"] = results[0].shp_path.parent
            raise RuntimeError("caller failed")
    assert not captured["folder"].exists()


def test_extraction_cap_is_enforced():
    files = {**FULL, "data.shp": b"s" * 100}
    with pytest.raises(UnsafeArchiveError) as info:
        with extract_shapefiles(make_zip(files), max_extract_bytes=50):
            pass
    assert info.value.details == {"limit_bytes": 50}


def test_corrupt_data_is_reported_as_corrupt_archive():
    # STORED (no compression) so the raw bytes are visible; flip them to break the CRC.
    good = make_zip({**FULL, "data.shp": b"A" * 100}, compression=zipfile.ZIP_STORED)
    bad = good.replace(b"A" * 100, b"B" * 100)
    with pytest.raises(CorruptArchiveError):
        with extract_shapefiles(bad):
            pass


def test_inspection_errors_still_apply():
    with pytest.raises(UnsafeArchiveError):
        with extract_shapefiles(make_zip({**FULL, "../evil.txt": b"x"})):
            pass