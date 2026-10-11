"""The benchmark generator must be valid, reproducible and well-formed."""

from __future__ import annotations

import zipfile

import pytest

from benchmarks.dataset_generator import build_geodataframe, write_shapefile_zip


@pytest.mark.parametrize("count", [1, 100, 1000])
def test_requested_count(count):
    assert len(build_geodataframe(count)) == count


@pytest.mark.parametrize(
    ("kind", "geom_type"),
    [("polygon", "Polygon"), ("line", "LineString"), ("point", "Point")],
)
def test_geometry_type_matches_kind(kind, geom_type):
    gdf = build_geodataframe(50, kind=kind)
    assert set(gdf.geometry.geom_type) == {geom_type}


def test_polygons_are_valid():
    assert build_geodataframe(500).geometry.is_valid.all()


def test_same_seed_same_data():
    first = build_geodataframe(100, seed=7)
    second = build_geodataframe(100, seed=7)
    assert first.geometry.equals(second.geometry)


def test_zip_contains_shapefile_parts(tmp_path):
    path = write_shapefile_zip(build_geodataframe(20), tmp_path / "out.zip")
    with zipfile.ZipFile(path) as archive:
        suffixes = {name.rsplit(".", 1)[-1] for name in archive.namelist()}
    assert {"shp", "shx", "dbf", "prj"} <= suffixes


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        build_geodataframe(10, kind="hexagon")