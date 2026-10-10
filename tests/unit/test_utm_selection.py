import pytest
from shapely.geometry import Point, Polygon

from app.core.exceptions import CRSResolutionError
from app.services.utm_selection import (
    lonlat_bounds,
    select_utm_for_bounds,
    utm_zone_for,
)


def test_hyderabad_is_zone_44_north():
    result = utm_zone_for(78.47, 17.38)
    assert result.zone == 44
    assert result.hemisphere == "N"
    assert result.label == "EPSG:32644"


def test_southern_hemisphere_uses_327xx():
    result = utm_zone_for(151.2, -33.87)  # Sydney
    assert result.zone == 56
    assert result.label == "EPSG:32756"


def test_zone_boundaries():
    assert utm_zone_for(77.999, 10).zone == 43
    assert utm_zone_for(78.0, 10).zone == 44


def test_lon_minus_180_is_zone_1():
    assert utm_zone_for(-180.0, 10).zone == 1


def test_lon_plus_180_is_zone_60():
    assert utm_zone_for(180.0, 10).zone == 60


def test_equator_is_north():
    assert utm_zone_for(78.47, 0.0).label == "EPSG:32644"


def test_central_longitude():
    assert utm_zone_for(78.47, 17.38).central_longitude == 81.0


def test_polar_north_rejected():
    with pytest.raises(CRSResolutionError) as exc_info:
        utm_zone_for(10.0, 85.0)
    assert exc_info.value.details["reason"] == "outside_utm_range"


def test_polar_south_rejected():
    with pytest.raises(CRSResolutionError) as exc_info:
        utm_zone_for(10.0, -81.0)
    assert exc_info.value.details["reason"] == "outside_utm_range"


def test_nan_rejected():
    with pytest.raises(CRSResolutionError) as exc_info:
        utm_zone_for(float("nan"), 10.0)
    assert exc_info.value.details["reason"] == "invalid_coordinates"


def test_out_of_range_longitude_rejected():
    with pytest.raises(CRSResolutionError) as exc_info:
        utm_zone_for(200.0, 10.0)
    assert exc_info.value.details["reason"] == "invalid_coordinates"


def test_bounds_from_points():
    bounds = lonlat_bounds([Point(78.0, 17.0), Point(79.0, 18.0)])
    assert bounds == (78.0, 17.0, 79.0, 18.0)


def test_bounds_ignore_none_and_empty():
    bounds = lonlat_bounds([None, Polygon(), Point(78.0, 17.0)])
    assert bounds == (78.0, 17.0, 78.0, 17.0)


def test_bounds_none_when_nothing_usable():
    assert lonlat_bounds([None, Polygon()]) is None


def test_select_for_bounds_uses_centre():
    result = select_utm_for_bounds((78.4, 17.3, 78.5, 17.5))
    assert result.label == "EPSG:32644"