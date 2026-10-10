from __future__ import annotations

from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)

from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.services.geometry_validation import (
    REASON_EMPTY,
    REASON_NON_FINITE,
    REASON_UNKNOWN_TYPE,
    validate_dataset,
)

SQUARE = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
BOWTIE = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])


def make_dataset(*geometries) -> ParsedDataset:
    features = tuple(Feature(index=i, geometry=g) for i, g in enumerate(geometries))
    return ParsedDataset(
        source_name="t.kml",
        source_kind=FileKind.KML,
        features=features,
        crs_text="EPSG:4326",
    )


def test_valid_geometry_is_unchanged_and_not_flagged():
    ds, report = validate_dataset(make_dataset(SQUARE, Point(1, 2)))
    assert report.valid == 2
    assert report.repaired == 0
    assert report.skipped == 0
    assert ds.features[0].geometry is SQUARE
    assert not ds.features[0].repaired


def test_bowtie_is_repaired_and_flagged():
    ds, report = validate_dataset(make_dataset(BOWTIE))
    feature = ds.features[0]
    assert feature.repaired
    assert not feature.is_skipped
    assert feature.geometry.is_valid
    assert report.repaired == 1


def test_repair_may_change_type_to_multipolygon():
    ds, _ = validate_dataset(make_dataset(BOWTIE))
    assert isinstance(ds.features[0].geometry, MultiPolygon)


def test_empty_polygon_is_skipped():
    ds, report = validate_dataset(make_dataset(Polygon()))
    assert ds.features[0].is_skipped
    assert report.skip_reasons == {REASON_EMPTY: 1}


def test_empty_linestring_from_kml_is_skipped():
    ds, report = validate_dataset(make_dataset(LineString()))
    assert ds.features[0].is_skipped
    assert report.skipped == 1


def test_linear_ring_is_skipped_as_unknown_type():
    ring = LinearRing([(0, 0), (1, 0), (1, 1)])
    ds, report = validate_dataset(make_dataset(ring))
    assert ds.features[0].is_skipped
    assert report.skip_reasons == {REASON_UNKNOWN_TYPE: 1}


def test_nan_coordinates_are_skipped():
    ds, report = validate_dataset(make_dataset(Point(float("nan"), 1)))
    assert ds.features[0].is_skipped
    assert report.skip_reasons == {REASON_NON_FINITE: 1}


def test_infinite_coordinates_are_skipped():
    ds, report = validate_dataset(make_dataset(LineString([(0, 0), (float("inf"), 1)])))
    assert ds.features[0].is_skipped
    assert report.skip_reasons == {REASON_NON_FINITE: 1}


def test_null_geometry_left_as_is():
    feature = Feature(index=0, geometry=None, skip_reason="Feature has no geometry")
    dataset = ParsedDataset("t.zip", FileKind.ZIP_SHAPEFILE, (feature,), "EPSG:4326")
    ds, report = validate_dataset(dataset)
    assert ds.features[0] is feature
    assert report.skipped == 1
    assert report.skip_reasons == {"skipped_by_parser": 1}


def test_collection_drops_empty_parts_and_is_flagged():
    gc = GeometryCollection([SQUARE, Point()])
    ds, _ = validate_dataset(make_dataset(gc))
    feature = ds.features[0]
    assert not feature.is_skipped
    assert feature.repaired
    assert len(feature.geometry.geoms) == 1


def test_collection_with_only_empty_parts_is_skipped():
    gc = GeometryCollection([Point(), Polygon()])
    ds, report = validate_dataset(make_dataset(gc))
    assert ds.features[0].is_skipped
    assert report.skip_reasons == {REASON_EMPTY: 1}


def test_collection_with_invalid_part_is_repaired():
    gc = GeometryCollection([BOWTIE, Point(5, 5)])
    ds, _ = validate_dataset(make_dataset(gc))
    assert ds.features[0].repaired
    assert ds.features[0].geometry.is_valid


def test_one_bad_feature_does_not_stop_others():
    ds, report = validate_dataset(make_dataset(SQUARE, Polygon(), BOWTIE, Point(1, 1)))
    assert report.total == 4
    assert report.valid == 2
    assert report.repaired == 1
    assert report.skipped == 1


def test_original_dataset_not_mutated():
    original = make_dataset(BOWTIE)
    validate_dataset(original)
    assert original.features[0].geometry is BOWTIE
    assert not original.features[0].repaired


def test_report_counts_add_up():
    _, report = validate_dataset(make_dataset(SQUARE, BOWTIE, Polygon(), Point()))
    assert report.valid + report.repaired + report.skipped == report.total


def test_report_counts_geometry_collections():
    gc = GeometryCollection([SQUARE, Point(1, 1)])
    _, report = validate_dataset(make_dataset(gc, SQUARE))
    assert report.geometry_collections == 1


def test_invalid_counts_repaired_bowtie():
    _, report = validate_dataset(make_dataset(BOWTIE, SQUARE))
    assert report.invalid == 1
    assert report.repaired == 1


def test_collection_with_empty_part_is_repaired_but_not_invalid():
    gc = GeometryCollection([SQUARE, Point()])
    _, report = validate_dataset(make_dataset(gc))
    assert report.repaired == 1
    assert report.invalid == 0


def test_empty_and_nan_features_are_not_counted_as_invalid():
    _, report = validate_dataset(make_dataset(Polygon(), Point(float("nan"), 1)))
    assert report.skipped == 2
    assert report.invalid == 0


def test_collection_with_invalid_part_counts_as_invalid_and_collection():
    gc = GeometryCollection([BOWTIE, Point(5, 5)])
    _, report = validate_dataset(make_dataset(gc))
    assert report.invalid == 1
    assert report.geometry_collections == 1