import pytest
from shapely.geometry import Point, Polygon

from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.domain.enums.geometry_kind import GeometryKind


@pytest.mark.parametrize(
    ("geom_type", "kind"),
    [
        ("Point", GeometryKind.POINT),
        ("MultiPoint", GeometryKind.MULTI_POINT),
        ("LineString", GeometryKind.LINE_STRING),
        ("MultiLineString", GeometryKind.MULTI_LINE_STRING),
        ("Polygon", GeometryKind.POLYGON),
        ("MultiPolygon", GeometryKind.MULTI_POLYGON),
        ("GeometryCollection", GeometryKind.GEOMETRY_COLLECTION),
    ],
)
def test_kind_from_shapely_type(geom_type, kind):
    assert GeometryKind.from_geom_type(geom_type) == kind


def test_unrecognised_type_is_unknown():
    assert GeometryKind.from_geom_type("LinearRing") == GeometryKind.UNKNOWN


def test_feature_kind_from_geometry():
    assert Feature(index=0, geometry=Point(1, 2)).kind == GeometryKind.POINT


def test_null_geometry_has_null_kind():
    assert Feature(index=0, geometry=None).kind == GeometryKind.NULL


def test_empty_geometry_is_detected():
    feature = Feature(index=0, geometry=Polygon())
    assert feature.is_empty is True
    assert feature.kind == GeometryKind.POLYGON


def test_is_skipped_follows_skip_reason():
    assert Feature(index=0, geometry=Point(1, 2)).is_skipped is False
    assert Feature(index=0, geometry=None, skip_reason="no geometry").is_skipped is True


def test_with_skip_reason_returns_copy_and_leaves_original():
    original = Feature(index=3, geometry=Point(1, 2), properties={"a": 1})
    skipped = original.with_skip_reason("bad")
    assert skipped.skip_reason == "bad"
    assert skipped.index == 3
    assert skipped.properties == {"a": 1}
    assert original.skip_reason is None


def test_properties_default_is_not_shared():
    a = Feature(index=0, geometry=None)
    b = Feature(index=1, geometry=None)
    a.properties["x"] = 1
    assert b.properties == {}


def test_dataset_counts_features():
    features = (Feature(0, Point(0, 0)), Feature(1, Point(1, 1)))
    ds = ParsedDataset("a.kml", FileKind.KML, features, crs_text="EPSG:4326")
    assert ds.feature_count == 2


def test_dataset_counts_skipped_features():
    features = (
        Feature(0, Point(0, 0)),
        Feature(1, None, skip_reason="no geometry"),
    )
    ds = ParsedDataset("a.kml", FileKind.KML, features, crs_text=None)
    assert ds.skipped_count == 1