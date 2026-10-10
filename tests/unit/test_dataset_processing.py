"""Tests for the processing pipeline (Step 10, Part 1)."""

import pytest
from shapely.geometry import LineString, Point, Polygon, box

from app.core.exceptions import CRSResolutionError
from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.domain.enums.geometry_kind import GeometryKind
from app.services.dataset_processing import process_dataset

SQUARE = box(78.40, 17.40, 78.41, 17.41)
LINE = LineString([(78.40, 17.40), (78.41, 17.41)])
BOWTIE = Polygon([(78.40, 17.40), (78.41, 17.41), (78.41, 17.40), (78.40, 17.41)])


def _dataset(geoms, crs_text="EPSG:4326", properties=None, warnings=()):
    features = tuple(
        Feature(
            index=i,
            geometry=g,
            properties=(properties[i] if properties else {}),
        )
        for i, g in enumerate(geoms)
    )
    return ParsedDataset(
        source_name="test.kml",
        source_kind=FileKind.KML,
        features=features,
        crs_text=crs_text,
        warnings=warnings,
    )


def test_utm_dataset_measures_polygon_and_line():
    result = process_dataset(_dataset([SQUARE, LINE]))
    assert result.target.strategy == "utm"
    assert result.measured_count == 2
    assert result.total_area_m2 > 0
    assert result.total_length_m > 0
    assert result.max_abs_area_diff_pct is not None
    assert result.max_abs_area_diff_pct < 0.5


def test_features_keep_input_order_and_properties():
    props = [{"name": "plot A"}, {"name": "road B"}]
    result = process_dataset(_dataset([SQUARE, LINE], properties=props))
    assert [f.index for f in result.features] == [0, 1]
    assert result.features[0].properties == {"name": "plot A"}
    assert result.features[1].properties == {"name": "road B"}


def test_point_counts_as_measured_without_values():
    result = process_dataset(_dataset([Point(78.4, 17.4), SQUARE]))
    point = result.features[0]
    assert point.status == "measured"
    assert point.cross_check is None
    assert result.area_calculations == 1
    assert result.length_calculations == 0


def test_empty_geometry_is_skipped_and_counted():
    result = process_dataset(_dataset([Polygon(), SQUARE]))
    assert result.skipped_count == 1
    assert result.measured_count == 1
    skipped = result.features[0]
    assert skipped.status == "skipped"
    assert skipped.reason is not None
    assert "empty" in skipped.reason.lower()
    assert result.validation.skipped == 1


def test_invalid_polygon_is_repaired_and_measured():
    result = process_dataset(_dataset([BOWTIE]))
    feature = result.features[0]
    assert feature.repaired is True
    assert feature.status == "measured"
    assert feature.measurement is not None
    assert feature.measurement.area_m2 > 0
    assert result.validation.repaired == 1


def test_missing_crs_fails_by_default():
    with pytest.raises(CRSResolutionError) as excinfo:
        process_dataset(_dataset([SQUARE], crs_text=None))
    assert excinfo.value.details["reason"] == "missing_crs"


def test_missing_crs_can_be_assumed_when_opted_in():
    result = process_dataset(
        _dataset([SQUARE], crs_text=None), assume_wgs84_if_missing=True
    )
    assert result.target.source_assumed is True
    assert any("EPSG:4326" in w for w in result.warnings)
    assert result.measured_count == 1


def test_all_features_skipped_fails_with_clear_reason():
    with pytest.raises(CRSResolutionError) as excinfo:
        process_dataset(_dataset([Polygon()]))
    assert excinfo.value.details["reason"] == "no_usable_geometries"


def test_equal_area_dataset_reports_geodesic_lengths():
    line = LineString([(0, 0), (1, 0)])
    far_polygon = box(40, 0, 41, 1)
    result = process_dataset(_dataset([line, far_polygon]))
    assert result.target.strategy == "laea"
    assert result.features[0].length_method == "geodesic"


def test_utm_offset_threshold_is_passed_through():
    # The square sits about 2.6 deg from the zone-44 centre line (81 E).
    default = process_dataset(_dataset([SQUARE]))
    strict = process_dataset(_dataset([SQUARE]), max_utm_offset_deg=2.0)
    assert default.target.strategy == "utm"
    assert strict.target.strategy == "laea"


def test_totals_match_feature_sums():
    result = process_dataset(_dataset([SQUARE, SQUARE, LINE]))
    area_sum = sum(
        f.measurement.area_m2 for f in result.features if f.measurement.area_m2
    )
    length_sum = sum(
        f.measurement.length_m for f in result.features if f.measurement.length_m
    )
    assert result.total_area_m2 == pytest.approx(area_sum)
    assert result.total_length_m == pytest.approx(length_sum)


def test_kind_counts():
    result = process_dataset(_dataset([SQUARE, SQUARE, LINE, Point(78.4, 17.4)]))
    assert result.kind_counts[GeometryKind.POLYGON] == 2
    assert result.kind_counts[GeometryKind.LINE_STRING] == 1
    assert result.kind_counts[GeometryKind.POINT] == 1
    assert result.feature_count == 4


def test_native_projected_dataset_is_not_reprojected():
    square = box(500000, 3000000, 500100, 3000100)  # 100 m x 100 m, UTM 44N
    result = process_dataset(_dataset([square], crs_text="EPSG:32644"))
    assert result.target.strategy == "native_projected"
    assert result.target.needs_reprojection is False
    assert result.features[0].measurement.area_m2 == pytest.approx(10000.0, rel=1e-6)


def test_duration_is_recorded():
    result = process_dataset(_dataset([SQUARE]))
    assert result.duration_ms >= 0


def test_warnings_combine_dataset_and_crs_warnings():
    result = process_dataset(
        _dataset([SQUARE], crs_text=None, warnings=("parser note",)),
        assume_wgs84_if_missing=True,
    )
    assert "parser note" in result.warnings
    assert len(result.warnings) >= 2


def test_validation_report_is_attached():
    result = process_dataset(_dataset([SQUARE, Polygon(), BOWTIE]))
    assert result.validation.total == 3
    assert result.validation.skipped == 1
    assert result.validation.repaired == 1