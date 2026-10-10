import pytest

from app.core.exceptions import CorruptKMLError
from app.domain.enums.file_kind import FileKind
from app.domain.enums.geometry_kind import GeometryKind
from app.services.kml_parser import parse_kml

NS = 'xmlns="http://www.opengis.net/kml/2.2"'


def kml(body: str, ns: str = NS) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><kml {ns}><Document>{body}</Document></kml>'
    ).encode()


def pm(geometry: str, name: str = "p") -> str:
    return f"<Placemark><name>{name}</name>{geometry}</Placemark>"


def point(coords: str) -> str:
    return f"<Point><coordinates>{coords}</coordinates></Point>"


def test_point_with_metadata():
    ds = parse_kml(kml(pm(point("78.4,17.4,0"), "Hyderabad")), "a.kml")
    f = ds.features[0]
    assert (f.geometry.x, f.geometry.y) == (78.4, 17.4)
    assert f.kind == GeometryKind.POINT
    assert f.properties["name"] == "Hyderabad"
    assert ds.crs_text == "EPSG:4326"
    assert ds.source_kind == FileKind.KML
    assert ds.source_name == "a.kml"


def test_altitude_is_dropped():
    assert parse_kml(kml(pm(point("78.4,17.4,500")))).features[0].geometry.has_z is False


def test_linestring():
    body = pm("<LineString><coordinates>0,0 1,1 2,0</coordinates></LineString>")
    f = parse_kml(kml(body)).features[0]
    assert f.kind == GeometryKind.LINE_STRING
    assert len(f.geometry.coords) == 3


def test_polygon_with_hole():
    body = pm(
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
        "0,0 10,0 10,10 0,10 0,0</coordinates></LinearRing></outerBoundaryIs>"
        "<innerBoundaryIs><LinearRing><coordinates>"
        "2,2 4,2 4,4 2,4 2,2</coordinates></LinearRing></innerBoundaryIs></Polygon>"
    )
    f = parse_kml(kml(body)).features[0]
    assert f.kind == GeometryKind.POLYGON
    assert f.geometry.area == pytest.approx(96.0)  # 100 minus the 2x2 hole


def test_multigeometry_of_polygons_is_multipolygon():
    square = (
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
        "{a},{a} {b},{a} {b},{b} {a},{b} {a},{a}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
    )
    body = pm(f"<MultiGeometry>{square.format(a=0, b=1)}{square.format(a=5, b=6)}</MultiGeometry>")
    assert parse_kml(kml(body)).features[0].kind == GeometryKind.MULTI_POLYGON


def test_multigeometry_of_points_is_multipoint():
    body = pm(f"<MultiGeometry>{point('1,1')}{point('2,2')}</MultiGeometry>")
    assert parse_kml(kml(body)).features[0].kind == GeometryKind.MULTI_POINT


def test_mixed_multigeometry_is_geometry_collection():
    line = "<LineString><coordinates>0,0 1,1</coordinates></LineString>"
    body = pm(f"<MultiGeometry>{point('1,1')}{line}</MultiGeometry>")
    assert parse_kml(kml(body)).features[0].kind == GeometryKind.GEOMETRY_COLLECTION


def test_placemarks_in_nested_folders_are_found_in_order():
    body = (
        "<Folder><Folder>" + pm(point("1,1"), "a") + "</Folder>" + pm(point("2,2"), "b") + "</Folder>"
    )
    ds = parse_kml(kml(body))
    assert [f.index for f in ds.features] == [0, 1]
    assert [f.properties["name"] for f in ds.features] == ["a", "b"]


def test_kml_without_namespace_works():
    ds = parse_kml(b"<kml><Placemark><Point><coordinates>1,2</coordinates></Point></Placemark></kml>")
    assert ds.feature_count == 1


def test_placemark_without_geometry_is_skipped():
    f = parse_kml(kml("<Placemark><name>x</name></Placemark>")).features[0]
    assert f.kind == GeometryKind.NULL
    assert f.is_skipped


def test_one_bad_placemark_does_not_kill_the_file():
    body = pm(point("abc,def"), "bad") + pm(point("1,2"), "good")
    ds = parse_kml(kml(body))
    assert ds.feature_count == 2
    assert ds.skipped_count == 1
    assert ds.features[0].skip_reason.startswith("Could not parse geometry")
    assert ds.features[1].geometry is not None


def test_out_of_range_coordinates_are_skipped():
    f = parse_kml(kml(pm(point("10,95")))).features[0]
    assert f.is_skipped
    assert "out of range" in f.skip_reason


def test_extended_data_and_simple_data_become_properties():
    body = (
        "<Placemark><name>x</name><ExtendedData>"
        '<Data name="owner"><value>Asha</value></Data>'
        '<SchemaData><SimpleData name="plot">12</SimpleData></SchemaData>'
        f"</ExtendedData>{point('1,2')}</Placemark>"
    )
    props = parse_kml(kml(body)).features[0].properties
    assert props["owner"] == "Asha"
    assert props["plot"] == "12"


def test_newlines_and_spaces_after_commas_are_tolerated():
    body = pm("<LineString><coordinates>\n  0, 0\n  1, 1\n</coordinates></LineString>")
    assert len(parse_kml(kml(body)).features[0].geometry.coords) == 2


def test_unsupported_gx_track_is_skipped_with_reason():
    ns = NS + ' xmlns:gx="http://www.google.com/kml/ext/2.2"'
    f = parse_kml(kml(pm("<gx:Track></gx:Track>"), ns)).features[0]
    assert f.is_skipped
    assert "unsupported" in f.skip_reason


def test_polygon_without_outer_boundary_is_skipped():
    f = parse_kml(kml(pm("<Polygon></Polygon>"))).features[0]
    assert f.is_skipped


def test_linestring_with_one_point_is_skipped():
    f = parse_kml(kml(pm("<LineString><coordinates>1,1</coordinates></LineString>"))).features[0]
    assert f.is_skipped


def test_empty_linestring_becomes_empty_geometry_not_skipped():
    f = parse_kml(kml(pm("<LineString><coordinates></coordinates></LineString>"))).features[0]
    assert f.kind == GeometryKind.LINE_STRING
    assert f.is_empty


def test_malformed_xml_raises_corrupt_kml():
    with pytest.raises(CorruptKMLError):
        parse_kml(b"<kml><Placemark>")


def test_non_kml_xml_is_rejected():
    with pytest.raises(CorruptKMLError):
        parse_kml(b"<html><body/></html>")


def test_entity_expansion_attack_is_blocked():
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;">]><kml><Placemark><name>&lol2;</name></Placemark></kml>'
    )
    with pytest.raises(CorruptKMLError):
        parse_kml(bomb)


def test_kml_with_no_placemarks_gives_warning():
    ds = parse_kml(kml(""))
    assert ds.feature_count == 0
    assert len(ds.warnings) == 1