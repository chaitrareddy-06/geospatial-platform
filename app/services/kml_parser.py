"""Parse KML bytes into a ParsedDataset.

KML coordinates are always lon,lat[,alt] in EPSG:4326. XML is parsed with
defusedxml, which blocks entity-expansion attacks ("billion laughs").
One bad Placemark never fails the whole file: it becomes a skipped Feature.
"""

import math
import re
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from shapely.errors import ShapelyError
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import CorruptKMLError
from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind

KML_CRS = "EPSG:4326"
MAX_NESTING = 20

_GEOMETRY_TAGS = {"Point", "LineString", "LinearRing", "Polygon", "MultiGeometry"}
_UNSUPPORTED_TAGS = {"Model", "Track", "MultiTrack"}


def _local(tag: Any) -> str:
    """Tag name without its namespace."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element: Element, name: str) -> list[Element]:
    return [c for c in element if _local(c.tag) == name]


def _child(element: Element, name: str) -> Element | None:
    found = _children(element, name)
    return found[0] if found else None


def _text(element: Element, name: str) -> str | None:
    child = _child(element, name)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _parse_coordinates(text: str | None) -> list[tuple[float, float]]:
    if not text:
        return []
    text = re.sub(r"\s*,\s*", ",", text.strip())  # tolerate "1, 2" style spacing
    coords: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            raise ValueError(f"bad coordinate tuple '{token}'")
        lon, lat = float(parts[0]), float(parts[1])
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise ValueError(f"non-finite coordinate '{token}'")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(f"coordinate out of range '{token}'")
        coords.append((lon, lat))  # altitude (parts[2]) is ignored
    return coords


def _coords_of(element: Element) -> list[tuple[float, float]]:
    return _parse_coordinates(_text(element, "coordinates"))


def _combine(parts: list[BaseGeometry]) -> BaseGeometry:
    types = {p.geom_type for p in parts}
    if types == {"Point"}:
        return MultiPoint(parts)
    if types == {"LineString"}:
        return MultiLineString(parts)
    if types == {"Polygon"}:
        return MultiPolygon(parts)
    return GeometryCollection(parts)


def _parse_geometry(element: Element, depth: int = 0) -> BaseGeometry:
    tag = _local(element.tag)

    if tag == "Point":
        coords = _coords_of(element)
        if not coords:
            return Point()
        if len(coords) > 1:
            raise ValueError("Point has more than one coordinate")
        return Point(coords[0])

    if tag in ("LineString", "LinearRing"):
        coords = _coords_of(element)
        return LineString(coords) if coords else LineString()

    if tag == "Polygon":
        outer = _child(element, "outerBoundaryIs")
        ring = _child(outer, "LinearRing") if outer is not None else None
        if ring is None:
            raise ValueError("Polygon has no outer boundary")
        shell = _coords_of(ring)
        if not shell:
            return Polygon()
        holes = []
        for inner in _children(element, "innerBoundaryIs"):
            hole_ring = _child(inner, "LinearRing")
            if hole_ring is not None:
                hole = _coords_of(hole_ring)
                if hole:
                    holes.append(hole)
        return Polygon(shell, holes)

    if tag == "MultiGeometry":
        if depth >= MAX_NESTING:
            raise ValueError("MultiGeometry is nested too deeply")
        parts = [
            _parse_geometry(c, depth + 1) for c in element if _local(c.tag) in _GEOMETRY_TAGS
        ]
        return _combine(parts)

    raise ValueError(f"unsupported geometry element '{tag}'")


def _extract_properties(placemark: Element) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key in ("name", "description"):
        value = _text(placemark, key)
        if value is not None:
            props[key] = value

    extended = _child(placemark, "ExtendedData")
    if extended is not None:
        for data in _children(extended, "Data"):
            key = data.get("name")
            if key:
                props[key] = _text(data, "value")
        for node in extended.iter():
            if _local(node.tag) == "SimpleData":
                key = node.get("name")
                if key:
                    props[key] = (node.text or "").strip()
    return props


def _parse_placemark(index: int, placemark: Element) -> Feature:
    props = _extract_properties(placemark)
    geometry_elements = [c for c in placemark if _local(c.tag) in _GEOMETRY_TAGS]

    if not geometry_elements:
        unsupported = [_local(c.tag) for c in placemark if _local(c.tag) in _UNSUPPORTED_TAGS]
        reason = (
            f"unsupported geometry element: {unsupported[0]}"
            if unsupported
            else "Placemark has no geometry"
        )
        return Feature(index=index, geometry=None, properties=props, skip_reason=reason)

    try:
        if len(geometry_elements) == 1:
            geometry = _parse_geometry(geometry_elements[0])
        else:  # invalid-but-common: several geometries directly in one Placemark
            geometry = _combine([_parse_geometry(e) for e in geometry_elements])
    except (ValueError, TypeError, ShapelyError) as exc:
        return Feature(
            index=index,
            geometry=None,
            properties=props,
            skip_reason=f"Could not parse geometry: {exc}",
        )
    return Feature(index=index, geometry=geometry, properties=props)


def parse_kml(content: bytes, source_name: str = "upload.kml") -> ParsedDataset:
    try:
        root = fromstring(content)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise CorruptKMLError(details={"reason": str(exc)}) from exc

    if _local(root.tag) != "kml":
        raise CorruptKMLError(
            "The file is XML but not a KML document.",
            details={"root_element": _local(root.tag)},
        )

    placemarks = [e for e in root.iter() if _local(e.tag) == "Placemark"]
    features = tuple(_parse_placemark(i, pm) for i, pm in enumerate(placemarks))

    warnings: tuple[str, ...] = ()
    if not features:
        warnings = ("The KML file contains no Placemark elements.",)

    return ParsedDataset(
        source_name=source_name,
        source_kind=FileKind.KML,
        features=features,
        crs_text=KML_CRS,
        warnings=warnings,
    )