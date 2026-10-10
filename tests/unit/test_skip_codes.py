"""Tests for stable skip codes (Step 10, Part 1c)."""

from collections import Counter

from shapely.geometry import Polygon, box

from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.services.dataset_processing import process_dataset

SQUARE = box(78.40, 17.40, 78.41, 17.41)


def _dataset(features):
    return ParsedDataset(
        source_name="test.kml",
        source_kind=FileKind.KML,
        features=tuple(features),
        crs_text="EPSG:4326",
    )


def test_feature_skip_code_defaults_to_none():
    assert Feature(index=0, geometry=SQUARE).skip_code is None


def test_with_skip_reason_stores_the_code():
    feature = Feature(index=0, geometry=None).with_skip_reason("a sentence", code="a_code")
    assert feature.skip_reason == "a sentence"
    assert feature.skip_code == "a_code"


def test_with_skip_reason_without_code_still_works():
    feature = Feature(index=0, geometry=None).with_skip_reason("a sentence")
    assert feature.skip_reason == "a sentence"
    assert feature.skip_code is None


def test_empty_geometry_gets_stable_code():
    result = process_dataset(
        _dataset([Feature(0, Polygon()), Feature(1, SQUARE)])
    )
    assert result.features[0].reason_code == "empty_geometry"
    assert result.features[0].reason is not None


def test_measured_feature_has_no_reason_code():
    result = process_dataset(_dataset([Feature(0, SQUARE)]))
    assert result.features[0].status == "measured"
    assert result.features[0].reason_code is None


def test_parser_skipped_feature_gets_parser_code():
    parser_skipped = Feature(1, SQUARE, skip_reason="bad attribute table row")
    result = process_dataset(_dataset([Feature(0, SQUARE), parser_skipped]))
    assert result.features[1].status == "skipped"
    assert result.features[1].reason_code == "skipped_by_parser"


def test_parser_reason_is_kept_even_if_geometry_is_empty():
    parser_skipped = Feature(0, Polygon(), skip_reason="parser said no")
    result = process_dataset(_dataset([parser_skipped, Feature(1, SQUARE)]))
    assert result.features[0].reason == "parser said no"
    assert result.features[0].reason_code == "skipped_by_parser"
    assert result.validation.skip_reasons == {"skipped_by_parser": 1}


def test_feature_codes_match_report_counts():
    features = [
        Feature(0, Polygon()),
        Feature(1, Polygon()),
        Feature(2, SQUARE),
        Feature(3, SQUARE, skip_reason="parser skip"),
    ]
    result = process_dataset(_dataset(features))
    from_features = Counter(
        f.reason_code for f in result.features if f.status == "skipped"
    )
    assert dict(from_features) == result.validation.skip_reasons