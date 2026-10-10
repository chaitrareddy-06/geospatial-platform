import numpy as np
import pytest
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import LinearRing, LineString, Point, Polygon, box

from app.core.exceptions import GeometryProcessingError
from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.domain.enums.geometry_kind import GeometryKind
from app.services.measurement import build_transformer, measure_geometry
from app.services.target_crs import resolve_target_crs

GEOD = Geod(ellps="WGS84")


def make_dataset(geometries, crs_text):
    features = tuple(Feature(index=i, geometry=g) for i, g in enumerate(geometries))
    return ParsedDataset(
        source_name="test",
        source_kind=FileKind.KML,
        features=features,
        crs_text=crs_text,
    )


def test_native_metre_polygon_area():
    result = measure_geometry(box(0, 0, 100, 200), transformer=None)
    assert result.kind is GeometryKind.POLYGON
    assert result.area_m2 == pytest.approx(20000.0)
    assert result.length_m is None


def test_polygon_hole_is_subtracted():
    donut = Polygon(box(0, 0, 100, 100).exterior.coords, [box(10, 10, 20, 20).exterior.coords])
    assert measure_geometry(donut, None).area_m2 == pytest.approx(9900.0)


def test_linestring_length():
    result = measure_geometry(LineString([(0, 0), (3, 4)]), None)
    assert result.kind is GeometryKind.LINE_STRING
    assert result.length_m == pytest.approx(5.0)
    assert result.area_m2 is None


def test_point_has_no_measurement():
    result = measure_geometry(Point(1, 2), None)
    assert result.kind is GeometryKind.POINT
    assert result.area_m2 is None
    assert result.length_m is None


def test_feet_area_is_converted_to_square_metres():
    result = measure_geometry(box(0, 0, 1, 1), None, meters_per_unit=0.3048)
    assert result.area_m2 == pytest.approx(0.3048**2)


def test_feet_length_is_converted_to_metres():
    result = measure_geometry(LineString([(0, 0), (100, 0)]), None, meters_per_unit=0.3048)
    assert result.length_m == pytest.approx(30.48)


def test_geographic_polygon_matches_geodesic_area():
    square = box(78.4, 17.3, 78.41, 17.31)
    target = resolve_target_crs(make_dataset([square], "EPSG:4326"))
    result = measure_geometry(square, build_transformer(target), target.meters_per_unit)
    geodesic_area, _ = GEOD.geometry_area_perimeter(square)
    # UTM zone 44 is ~2.6 deg from this square, so a ~0.1 percent gap is expected.
    assert result.area_m2 == pytest.approx(abs(geodesic_area), rel=3e-3)


def test_geographic_line_matches_geodesic_length():
    line = LineString([(78.4, 17.3), (78.5, 17.4)])
    target = resolve_target_crs(make_dataset([line], "EPSG:4326"))
    result = measure_geometry(line, build_transformer(target), target.meters_per_unit)
    assert result.length_m == pytest.approx(GEOD.geometry_length(line), rel=3e-3)


def test_build_transformer_is_none_for_native_projected():
    target = resolve_target_crs(make_dataset([Point(500000, 1900000)], "EPSG:32644"))
    assert build_transformer(target) is None


def test_build_transformer_exists_for_geographic_source():
    target = resolve_target_crs(make_dataset([Point(78.47, 17.38)], "EPSG:4326"))
    assert build_transformer(target) is not None


def test_linear_ring_is_unsupported_at_top_level():
    ring = LinearRing([(0, 0), (1, 0), (1, 1), (0, 0)])
    with pytest.raises(GeometryProcessingError) as exc_info:
        measure_geometry(ring, None)
    assert exc_info.value.details["reason"] == "unsupported_for_measurement"


def test_empty_geometry_raises():
    with pytest.raises(GeometryProcessingError) as exc_info:
        measure_geometry(Polygon(), None)
    assert exc_info.value.details["reason"] == "empty_geometry"


def test_none_geometry_raises():
    with pytest.raises(GeometryProcessingError) as exc_info:
        measure_geometry(None, None)
    assert exc_info.value.details["reason"] == "empty_geometry"


class _InfTransformer:
    """Stand-in for a pyproj Transformer that cannot transform any point (PROJ
    reports such points as inf instead of raising)."""

    def transform(self, x, y):
        return np.full_like(x, np.inf, dtype=float), np.full_like(y, np.inf, dtype=float)


def test_untransformable_coordinates_raise():
    line = LineString([(0, 0), (1, 1)])
    with pytest.raises(GeometryProcessingError) as exc_info:
        measure_geometry(line, _InfTransformer())  # type: ignore[arg-type]
    assert exc_info.value.details["reason"] == "reprojection_produced_invalid_coordinates"


def test_target_crs_carries_source_crs_object():
    target = resolve_target_crs(make_dataset([Point(78.47, 17.38)], "EPSG:4326"))
    assert target.source_crs.to_epsg() == 4326


def test_assumed_source_crs_is_4326():
    target = resolve_target_crs(
        make_dataset([Point(78.47, 17.38)], None), assume_wgs84_if_missing=True
    )
    assert target.source_crs.to_epsg() == 4326


def test_web_mercator_source_is_measured_in_utm_not_mercator():
    lonlat_square = box(78.4, 17.3, 78.41, 17.31)
    to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    def convert(coords: np.ndarray) -> np.ndarray:
        x, y = to_mercator.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    mercator_square = shapely.transform(lonlat_square, convert)
    target = resolve_target_crs(make_dataset([mercator_square], "EPSG:3857"))
    assert target.measurement_label == "EPSG:32644"

    result = measure_geometry(
        mercator_square, build_transformer(target), target.meters_per_unit
    )
    geodesic_area, _ = GEOD.geometry_area_perimeter(lonlat_square)
    assert result.area_m2 == pytest.approx(abs(geodesic_area), rel=3e-3)
    # Naive Mercator area would be about 5 percent too big at this latitude.
    assert mercator_square.area > abs(geodesic_area) * 1.04