import io
import zipfile
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from app.core.exceptions import (
    CorruptShapefileError,
    MissingShapefileComponentError,
)
from app.domain.enums.file_kind import FileKind
from app.services.shapefile_parser import _to_python, parse_shapefile_zip


def make_zip(tmp_path, layers: dict[str, gpd.GeoDataFrame], with_prj: bool = True) -> bytes:
    folder = tmp_path / "src"
    folder.mkdir(exist_ok=True)
    for name, gdf in layers.items():
        gdf.to_file(folder / f"{name}.shp", driver="ESRI Shapefile")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in folder.iterdir():
            if with_prj or path.suffix != ".prj":
                zf.write(path, path.name)
    return buf.getvalue()


def square_gdf(crs="EPSG:4326") -> gpd.GeoDataFrame:
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    return gpd.GeoDataFrame({"name": ["plot-1"]}, geometry=[poly], crs=crs)


def test_polygon_shapefile_is_parsed(tmp_path):
    ds = parse_shapefile_zip(make_zip(tmp_path, {"data": square_gdf()}), "survey.zip")[0]
    assert ds.source_name == "survey.zip"
    assert ds.source_kind == FileKind.ZIP_SHAPEFILE
    assert ds.feature_count == 1
    feature = ds.features[0]
    assert feature.index == 0
    assert feature.geometry.area == pytest.approx(1.0)
    assert feature.properties["name"] == "plot-1"
    assert ds.warnings == ()


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:32644"])
def test_crs_is_read_from_prj(tmp_path, crs):
    ds = parse_shapefile_zip(make_zip(tmp_path, {"data": square_gdf(crs)}))[0]
    assert ds.crs_text == crs


def test_missing_prj_gives_none_crs_and_warning(tmp_path):
    ds = parse_shapefile_zip(make_zip(tmp_path, {"data": square_gdf()}, with_prj=False))[0]
    assert ds.crs_text is None
    assert len(ds.warnings) == 1
    assert ".prj" in ds.warnings[0]


def test_null_geometry_becomes_skipped_feature(tmp_path):
    gdf = gpd.GeoDataFrame(
        {"name": ["a", "b"]}, geometry=[Point(1, 1), None], crs="EPSG:4326"
    )
    ds = parse_shapefile_zip(make_zip(tmp_path, {"data": gdf}))[0]
    assert ds.feature_count == 2
    assert ds.skipped_count == 1
    assert ds.features[1].geometry is None
    assert ds.features[1].skip_reason == "Feature has no geometry"
    assert ds.features[1].index == 1


def test_attribute_values_are_plain_python_types(tmp_path):
    gdf = gpd.GeoDataFrame(
        {"n": [1, 2], "f": [1.5, 2.5], "s": ["a", "b"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:4326",
    )
    props = parse_shapefile_zip(make_zip(tmp_path, {"data": gdf}))[0].features[0].properties
    assert type(props["n"]) is int
    assert type(props["f"]) is float
    assert type(props["s"]) is str


def test_zip_with_several_shapefiles_returns_several_datasets(tmp_path):
    layers = {"a": square_gdf(), "b": square_gdf()}
    datasets = parse_shapefile_zip(make_zip(tmp_path, layers), "x.zip")
    assert [d.source_name for d in datasets] == ["x.zip:a", "x.zip:b"]


def test_unreadable_shapefile_raises_corrupt_shapefile_error():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.shp", b"this is not a shapefile")
        zf.writestr("data.shx", b"x")
        zf.writestr("data.dbf", b"d")
    with pytest.raises(CorruptShapefileError):
        parse_shapefile_zip(buf.getvalue())


def test_safety_checks_still_apply(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.shp", b"s")
        zf.writestr("data.shx", b"x")
    with pytest.raises(MissingShapefileComponentError):
        parse_shapefile_zip(buf.getvalue())


def test_corrupt_shapefile_error_attributes():
    err = CorruptShapefileError()
    assert (err.status_code, err.error_code) == (422, "corrupt_shapefile")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (np.int64(5), 5),
        (np.float64(1.5), 1.5),
        (float("nan"), None),
        (float("inf"), None),
        (pd.NaT, None),
        (pd.Timestamp("2024-01-02"), "2024-01-02T00:00:00"),
        (date(2024, 1, 2), "2024-01-02"),
        ("text", "text"),
    ],
)
def test_to_python_conversions(value, expected):
    assert _to_python(value) == expected