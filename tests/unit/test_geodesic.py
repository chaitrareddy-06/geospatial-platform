"""Tests for the geodesic cross-check (Step 9, Part 3)."""

import pytest
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.geometry.polygon import orient

from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.services.geodesic import (
    build_lonlat_transformer,
    geodesic_measure,
    measure_feature_checked,
)
from app.services.measurement import build_transformer
from app.services.target_crs import resolve_target_crs


def _dataset(geoms, crs_text="EPSG:4326"):
    features = tuple(Feature(index=i, geometry=g) for i, g in enumerate(geoms))
    return ParsedDataset(
        source_name="test.kml",
        source_kind=FileKind.KML,
        features=features,
        crs_text=crs_text,
    )


def _run(geoms, crs_text="EPSG:4326"):
    dataset = _dataset(geoms, crs_text)
    target = resolve_target_crs(dataset)
    transformer = build_transformer(target)
    lonlat = build_lonlat_transformer(target)
    checked = [
        measure_feature_checked(f, target, transformer, lonlat)
        for f in dataset.features
    ]
    return target, checked


# ---- geodesic_measure (pure) -------------------------------------------


def test_geodesic_area_of_one_degree_square_at_equator():
    result = geodesic_measure(box(0, 0, 1, 1))
    assert result.area_m2 == pytest.approx(1.2309e10, rel=0.005)
    assert result.length_m == 0.0


def test_geodesic_area_ignores_ring_direction():
    square = box(0, 0, 1, 1)
    ccw = geodesic_measure(orient(square, 1.0)).area_m2
    cw = geodesic_measure(orient(square, -1.0)).area_m2
    assert ccw == pytest.approx(cw)
    assert ccw > 0


def test_geodesic_area_subtracts_holes():
    shell = [(0, 0), (1, 0), (1, 1), (0, 1)]
    hole = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
    with_hole = geodesic_measure(Polygon(shell, [hole])).area_m2
    solid = geodesic_measure(Polygon(shell)).area_m2
    assert with_hole == pytest.approx(solid * 0.75, rel=0.01)


def test_geodesic_length_along_equator():
    result = geodesic_measure(LineString([(0, 0), (1, 0)]))
    assert result.length_m == pytest.approx(111319.5, rel=1e-3)
    assert result.area_m2 == 0.0


def test_geodesic_length_along_meridian():
    result = geodesic_measure(LineString([(0, 0), (0, 1)]))
    assert result.length_m == pytest.approx(110574.0, rel=2e-3)


def test_geodesic_multilinestring_sums_parts():
    a = LineString([(0, 0), (1, 0)])
    b = LineString([(0, 5), (1, 5)])
    total = geodesic_measure(MultiLineString([a, b])).length_m
    assert total == pytest.approx(
        geodesic_measure(a).length_m + geodesic_measure(b).length_m
    )


def test_geodesic_multipolygon_sums_parts():
    a = box(0, 0, 1, 1)
    b = box(5, 0, 6, 1)
    total = geodesic_measure(MultiPolygon([a, b])).area_m2
    assert total == pytest.approx(
        geodesic_measure(a).area_m2 + geodesic_measure(b).area_m2
    )


def test_geodesic_point_has_no_measurement():
    result = geodesic_measure(Point(10, 10))
    assert result.area_m2 == 0.0
    assert result.length_m == 0.0


def test_geodesic_collection_counts_polygons_and_lines():
    collection = GeometryCollection(
        [box(0, 0, 1, 1), LineString([(0, 5), (1, 5)]), Point(3, 3)]
    )
    result = geodesic_measure(collection)
    assert result.area_m2 > 0
    assert result.length_m > 0


def test_geodesic_linear_ring_is_ignored():
    ring = LinearRing([(0, 0), (1, 0), (1, 1), (0, 0)])
    result = geodesic_measure(ring)
    assert result.area_m2 == 0.0
    assert result.length_m == 0.0


# ---- measure_feature_checked --------------------------------------------


def test_utm_polygon_has_small_area_difference():
    target, checked = _run([box(78.40, 17.40, 78.41, 17.41)])
    assert target.strategy == "utm"
    cross = checked[0].cross_check
    assert cross is not None
    assert cross.area_diff_pct is not None
    assert abs(cross.area_diff_pct) < 0.5


def test_utm_line_keeps_projected_length():
    target, checked = _run([LineString([(78.40, 17.40), (78.41, 17.41)])])
    assert target.strategy == "utm"
    item = checked[0]
    assert item.length_method == "projected"
    assert item.cross_check is not None
    assert item.result.measurement.length_m == pytest.approx(
        item.cross_check.geodesic_length_m, rel=0.005
    )


def test_laea_dataset_reports_geodesic_length():
    line = LineString([(0, 0), (1, 0)])
    far_polygon = box(40, 0, 41, 1)
    target, checked = _run([line, far_polygon])
    assert target.strategy == "laea"
    line_item = checked[0]
    assert line_item.length_method == "geodesic"
    assert line_item.cross_check is not None
    assert line_item.result.measurement.length_m == pytest.approx(
        line_item.cross_check.geodesic_length_m
    )


def test_laea_polygon_area_stays_projected_and_matches_geodesic():
    line = LineString([(0, 0), (1, 0)])
    far_polygon = box(40, 0, 41, 1)
    _, checked = _run([line, far_polygon])
    cross = checked[1].cross_check
    assert cross is not None
    assert cross.area_diff_pct is not None
    assert abs(cross.area_diff_pct) < 1.0


def test_point_feature_has_no_cross_check():
    _, checked = _run([Point(78.4, 17.4), box(78.40, 17.40, 78.41, 17.41)])
    item = checked[0]
    assert item.result.status == "measured"
    assert item.cross_check is None
    assert item.length_method is None


def test_skipped_feature_passes_through_untouched():
    skipped = Feature(index=0, geometry=Polygon(), skip_reason="empty_geometry")
    valid = Feature(index=1, geometry=box(78.40, 17.40, 78.41, 17.41))
    dataset = ParsedDataset(
        source_name="test.kml",
        source_kind=FileKind.KML,
        features=(skipped, valid),
        crs_text="EPSG:4326",
    )
    target = resolve_target_crs(dataset)
    item = measure_feature_checked(
        skipped, target, build_transformer(target), build_lonlat_transformer(target)
    )
    assert item.result.status == "skipped"
    assert item.cross_check is None


def test_failing_cross_check_does_not_fail_the_feature():
    class BrokenTransformer:
        def transform(self, x, y):
            raise RuntimeError("boom")

    square = box(500000, 3000000, 500100, 3000100)  # 100 m x 100 m in UTM 44N
    dataset = _dataset([square], crs_text="EPSG:32644")
    target = resolve_target_crs(dataset)
    item = measure_feature_checked(
        dataset.features[0], target, build_transformer(target), BrokenTransformer()
    )
    assert item.result.status == "measured"
    assert item.result.measurement.area_m2 == pytest.approx(10000.0, rel=1e-6)
    assert item.cross_check is None