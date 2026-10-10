import numpy as np
import pytest
from pyproj import Geod
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.domain.enums.geometry_kind import GeometryKind
from app.services.measurement import (
    build_transformer,
    measure_feature,
    measure_geometry,
)
from app.services.target_crs import resolve_target_crs

GEOD = Geod(ellps="WGS84")


class _InfTransformer:
    def transform(self, x, y):
        return np.full_like(x, np.inf, dtype=float), np.full_like(y, np.inf, dtype=float)


class _BoomTransformer:
    def transform(self, x, y):
        raise RuntimeError("boom")


def test_multipolygon_sums_areas():
    multi = MultiPolygon([box(0, 0, 10, 10), box(20, 20, 25, 25)])
    result = measure_geometry(multi, None)
    assert result.kind is GeometryKind.MULTI_POLYGON
    assert result.area_m2 == pytest.approx(125.0)
    assert result.length_m is None
    assert result.part_count == 2


def test_multilinestring_sums_lengths():
    multi = MultiLineString([[(0, 0), (3, 4)], [(0, 0), (0, 10)]])
    result = measure_geometry(multi, None)
    assert result.kind is GeometryKind.MULTI_LINE_STRING
    assert result.length_m == pytest.approx(15.0)
    assert result.area_m2 is None
    assert result.part_count == 2


def test_multipoint_is_accepted_with_part_count_only():
    result = measure_geometry(MultiPoint([(0, 0), (1, 1), (2, 2)]), None)
    assert result.kind is GeometryKind.MULTI_POINT
    assert result.area_m2 is None
    assert result.length_m is None
    assert result.part_count == 3


def test_collection_with_polygon_line_and_point():
    collection = GeometryCollection(
        [box(0, 0, 10, 10), LineString([(0, 0), (3, 4)]), Point(1, 1)]
    )
    result = measure_geometry(collection, None)
    assert result.kind is GeometryKind.GEOMETRY_COLLECTION
    assert result.area_m2 == pytest.approx(100.0)
    assert result.length_m == pytest.approx(5.0)
    assert result.part_count == 3
    assert result.unsupported_parts == ()


def test_nested_collection_is_walked_recursively():
    inner = MultiPolygon([box(0, 0, 10, 10), box(20, 20, 25, 25)])
    collection = GeometryCollection([inner, Point(1, 1)])
    assert measure_geometry(collection, None).area_m2 == pytest.approx(125.0)


def test_collection_reports_unsupported_part_instead_of_failing():
    ring = LinearRing([(0, 0), (1, 0), (1, 1), (0, 0)])
    collection = GeometryCollection([box(0, 0, 10, 10), ring])
    result = measure_geometry(collection, None)
    assert result.area_m2 == pytest.approx(100.0)
    assert result.unsupported_parts == ("LinearRing",)


def test_collection_of_only_points_has_no_measurement():
    result = measure_geometry(GeometryCollection([Point(0, 0), Point(1, 1)]), None)
    assert result.area_m2 is None
    assert result.length_m is None


def test_multipolygon_in_feet_is_converted():
    multi = MultiPolygon([box(0, 0, 1, 1), box(5, 5, 6, 6)])
    result = measure_geometry(multi, None, meters_per_unit=0.3048)
    assert result.area_m2 == pytest.approx(2 * 0.3048**2)


def test_geographic_multipolygon_matches_sum_of_geodesic_areas():
    first = box(78.4, 17.3, 78.41, 17.31)
    second = box(78.45, 17.35, 78.46, 17.36)
    multi = MultiPolygon([first, second])
    dataset = ParsedDataset(
        source_name="test",
        source_kind=FileKind.KML,
        features=(Feature(index=0, geometry=multi),),
        crs_text="EPSG:4326",
    )
    target = resolve_target_crs(dataset)
    result = measure_geometry(multi, build_transformer(target), target.meters_per_unit)
    expected = sum(abs(GEOD.geometry_area_perimeter(p)[0]) for p in (first, second))
    assert result.area_m2 == pytest.approx(expected, rel=3e-3)


def test_measure_feature_measured():
    feature = Feature(index=3, geometry=box(0, 0, 10, 10))
    result = measure_feature(feature, None)
    assert result.status == "measured"
    assert result.index == 3
    assert result.measurement is not None
    assert result.measurement.area_m2 == pytest.approx(100.0)
    assert result.reason is None


def test_measure_feature_skipped_keeps_the_original_reason():
    feature = Feature(index=0, geometry=None, skip_reason="empty_geometry")
    result = measure_feature(feature, None)
    assert result.status == "skipped"
    assert result.reason == "empty_geometry"
    assert result.measurement is None


def test_measure_feature_failed_reprojection_is_recorded_not_raised():
    feature = Feature(index=0, geometry=LineString([(0, 0), (1, 1)]))
    result = measure_feature(feature, _InfTransformer())  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.reason == "reprojection_produced_invalid_coordinates"


def test_measure_feature_unexpected_error_is_recorded_not_raised():
    feature = Feature(index=0, geometry=LineString([(0, 0), (1, 1)]))
    result = measure_feature(feature, _BoomTransformer())  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.reason == "unexpected_error"


def test_measure_feature_carries_the_repaired_flag():
    feature = Feature(index=0, geometry=box(0, 0, 10, 10), repaired=True)
    assert measure_feature(feature, None).repaired is True


def test_measure_feature_empty_geometry_without_skip_reason_fails_cleanly():
    feature = Feature(index=0, geometry=Polygon())
    result = measure_feature(feature, None)
    assert result.status == "failed"
    assert result.reason == "empty_geometry"