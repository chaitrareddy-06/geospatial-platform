import numpy as np
import pytest
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import Point, Polygon, box

from app.core.exceptions import CRSResolutionError
from app.services.projection_strategy import (
    choose_projection,
    circular_lon_extent,
)


def test_circular_extent_simple():
    span, center = circular_lon_extent([78.0, 79.0])
    assert span == pytest.approx(1.0)
    assert center == pytest.approx(78.5)


def test_circular_extent_single_value():
    assert circular_lon_extent([78.0]) == (0.0, 78.0)


def test_circular_extent_across_antimeridian():
    span, center = circular_lon_extent([179.9, -179.9])
    assert span == pytest.approx(0.2, abs=1e-6)
    assert abs(center) == pytest.approx(180.0, abs=1e-6)


def test_local_dataset_picks_utm():
    choice = choose_projection([box(78.4, 17.3, 78.5, 17.5)])
    assert choice.strategy == "utm"
    assert choice.label == "EPSG:32644"
    assert choice.reason == "within_single_utm_zone"


def test_none_and_empty_geometries_are_ignored():
    choice = choose_projection([None, Polygon(), Point(78.47, 17.38)])
    assert choice.label == "EPSG:32644"


def test_no_usable_geometries_raises():
    with pytest.raises(CRSResolutionError) as exc_info:
        choose_projection([None, Polygon()])
    assert exc_info.value.details["reason"] == "no_usable_geometries"


def test_wide_dataset_uses_equal_area():
    choice = choose_projection([Point(70, 10), Point(90, 25)])
    assert choice.strategy == "laea"
    assert choice.preserves == "area"
    assert choice.label.startswith("LAEA(")


def test_polar_dataset_uses_equal_area():
    choice = choose_projection([Point(10, 85), Point(11, 86)])
    assert choice.strategy == "laea"
    assert choice.reason == "polar_latitudes"


def test_antimeridian_dataset_stays_utm():
    choice = choose_projection([Point(179.95, -17.0), Point(-179.95, -17.0)])
    assert choice.strategy == "utm"
    assert choice.label in {"EPSG:32701", "EPSG:32760"}
    assert choice.lon_span_deg == pytest.approx(0.1, abs=1e-6)


def test_small_dataset_straddling_zone_boundary_stays_utm():
    choice = choose_projection([Point(77.9, 17.0), Point(78.1, 17.0)])
    assert choice.strategy == "utm"
    assert choice.label == "EPSG:32644"


def test_dataset_spanning_two_zones_uses_equal_area():
    choice = choose_projection([Point(76.0, 17.0), Point(84.0, 17.0)])
    assert choice.strategy == "laea"
    assert choice.reason == "extent_exceeds_utm_zone"


def test_laea_area_matches_geodesic_area_for_a_small_box():
    small = box(79.9, 19.9, 80.1, 20.1)
    choice = choose_projection([Point(70, 10), Point(90, 30), small])
    assert choice.strategy == "laea"

    to_crs = Transformer.from_crs("EPSG:4326", choice.crs, always_xy=True)

    def reproject(coords: np.ndarray) -> np.ndarray:
        x, y = to_crs.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    projected_area = shapely.transform(small, reproject).area
    geodesic_area, _ = Geod(ellps="WGS84").geometry_area_perimeter(small)
    assert projected_area == pytest.approx(abs(geodesic_area), rel=1e-3)


def test_coordinates_outside_lonlat_range_raise():
    with pytest.raises(CRSResolutionError) as exc_info:
        choose_projection([Point(500000.0, 1900000.0)])
    assert exc_info.value.details["reason"] == "coordinates_not_lonlat"