import pytest
from pyproj import Transformer
from shapely.geometry import Point

from app.core.config import Settings
from app.core.exceptions import CRSResolutionError
from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.services.target_crs import resolve_target_crs


def make_dataset(geometries, crs_text):
    features = tuple(Feature(index=i, geometry=g) for i, g in enumerate(geometries))
    return ParsedDataset(
        source_name="test",
        source_kind=FileKind.KML,
        features=features,
        crs_text=crs_text,
    )


def test_geographic_local_dataset_uses_utm():
    result = resolve_target_crs(make_dataset([Point(78.47, 17.38)], "EPSG:4326"))
    assert result.strategy == "utm"
    assert result.measurement_label == "EPSG:32644"
    assert result.needs_reprojection is True
    assert result.source_label == "EPSG:4326"
    assert result.source_assumed is False


def test_geographic_wide_dataset_uses_equal_area():
    data = [Point(70, 10), Point(90, 25)]
    result = resolve_target_crs(make_dataset(data, "EPSG:4326"))
    assert result.strategy == "laea"
    assert result.needs_reprojection is True


def test_other_geographic_datum_is_accepted():
    result = resolve_target_crs(make_dataset([Point(78.47, 17.38)], "EPSG:4269"))
    assert result.strategy == "utm"
    assert result.source_label == "EPSG:4269"


def test_projected_utm_is_used_as_is():
    result = resolve_target_crs(make_dataset([Point(500000, 1900000)], "EPSG:32644"))
    assert result.strategy == "native_projected"
    assert result.measurement_label == "EPSG:32644"
    assert result.needs_reprojection is False
    assert result.meters_per_unit == pytest.approx(1.0)


def test_projected_feet_crs_keeps_unit_factor():
    result = resolve_target_crs(make_dataset([Point(3000000, 13000000)], "EPSG:2278"))
    assert result.strategy == "native_projected"
    assert result.meters_per_unit == pytest.approx(0.3048, rel=1e-3)


def test_web_mercator_is_not_trusted():
    to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x, y = to_mercator.transform(78.47, 17.38)
    result = resolve_target_crs(make_dataset([Point(x, y)], "EPSG:3857"))
    assert result.strategy == "utm"
    assert result.measurement_label == "EPSG:32644"
    assert result.needs_reprojection is True
    assert result.source_label == "EPSG:3857"
    assert any("Web Mercator" in w for w in result.warnings)


def test_missing_crs_fails_by_default():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_target_crs(make_dataset([Point(78.47, 17.38)], None))
    assert exc_info.value.details["reason"] == "missing_crs"


def test_missing_crs_assumed_when_opted_in_and_coordinates_fit():
    result = resolve_target_crs(
        make_dataset([Point(78.47, 17.38)], None), assume_wgs84_if_missing=True
    )
    assert result.source_assumed is True
    assert result.source_label == "EPSG:4326"
    assert result.strategy == "utm"
    assert len(result.warnings) == 1


def test_missing_crs_not_assumed_when_coordinates_look_projected():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_target_crs(
            make_dataset([Point(500000, 1900000)], None), assume_wgs84_if_missing=True
        )
    assert exc_info.value.details["reason"] == "missing_crs_not_assumable"


def test_invalid_crs_text_raises():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_target_crs(make_dataset([Point(78.47, 17.38)], "not a crs"))
    assert exc_info.value.details["reason"] == "invalid_crs"


def test_dataset_with_only_skipped_features_raises():
    skipped = Feature(index=0, geometry=None, skip_reason="Feature has no geometry")
    dataset = ParsedDataset(
        source_name="test",
        source_kind=FileKind.KML,
        features=(skipped,),
        crs_text="EPSG:4326",
    )
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_target_crs(dataset)
    assert exc_info.value.details["reason"] == "no_usable_geometries"


def test_skipped_features_do_not_influence_the_choice():
    far_away = Feature(index=0, geometry=Point(10, 50), skip_reason="skipped")
    kept = Feature(index=1, geometry=Point(78.47, 17.38))
    dataset = ParsedDataset(
        source_name="test",
        source_kind=FileKind.KML,
        features=(far_away, kept),
        crs_text="EPSG:4326",
    )
    assert resolve_target_crs(dataset).measurement_label == "EPSG:32644"


def test_utm_threshold_is_passed_through():
    data = [Point(78.5, 17.0), Point(83.5, 17.0)]
    dataset = make_dataset(data, "EPSG:4326")
    assert resolve_target_crs(dataset, max_utm_offset_deg=4.0).strategy == "utm"
    assert resolve_target_crs(dataset, max_utm_offset_deg=2.0).strategy == "laea"


def test_geographic_crs_with_projected_looking_coordinates_raises():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_target_crs(make_dataset([Point(500000, 1900000)], "EPSG:4326"))
    assert exc_info.value.details["reason"] == "coordinates_not_lonlat"


def test_setting_assume_wgs84_defaults_to_false():
    assert Settings().assume_wgs84_if_missing_crs is False


def test_setting_assume_wgs84_can_be_enabled():
    assert Settings(assume_wgs84_if_missing_crs=True).assume_wgs84_if_missing_crs is True