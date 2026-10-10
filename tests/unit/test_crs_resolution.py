import pytest
from pyproj import CRS

from app.core.exceptions import CRSResolutionError
from app.services.crs_resolution import resolve_crs


def test_epsg_4326_is_geographic():
    result = resolve_crs("EPSG:4326")
    assert result.is_geographic is True
    assert result.is_projected is False
    assert result.label == "EPSG:4326"


def test_utm_code_is_projected():
    result = resolve_crs("EPSG:32644")
    assert result.is_projected is True
    assert result.is_geographic is False


def test_wkt_text_is_accepted():
    wkt = CRS.from_epsg(4326).to_wkt()
    result = resolve_crs(wkt)
    assert result.is_geographic is True


def test_none_raises_missing_crs():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_crs(None)
    assert exc_info.value.error_code == "crs_resolution_failed"
    assert exc_info.value.details["reason"] == "missing_crs"


def test_blank_string_raises_missing_crs():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_crs("   ")
    assert exc_info.value.details["reason"] == "missing_crs"


def test_garbage_text_raises_invalid_crs():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_crs("this is not a crs")
    assert exc_info.value.details["reason"] == "invalid_crs"


def test_utm_unit_is_metres():
    assert resolve_crs("EPSG:32644").meters_per_unit == pytest.approx(1.0)


def test_feet_based_projected_crs_reports_foot_factor():
    # NAD83 / Texas South Central, in US survey feet
    result = resolve_crs("EPSG:2278")
    assert result.is_projected is True
    assert result.meters_per_unit == pytest.approx(0.3048, rel=1e-3)


def test_geographic_crs_has_no_linear_unit():
    assert resolve_crs("EPSG:4326").meters_per_unit is None


def test_geocentric_crs_is_rejected():
    with pytest.raises(CRSResolutionError) as exc_info:
        resolve_crs("EPSG:4978")
    assert exc_info.value.details["reason"] == "unsupported_crs_type"