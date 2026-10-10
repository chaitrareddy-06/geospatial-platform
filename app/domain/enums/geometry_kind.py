from enum import StrEnum


class GeometryKind(StrEnum):
    POINT = "Point"
    MULTI_POINT = "MultiPoint"
    LINE_STRING = "LineString"
    MULTI_LINE_STRING = "MultiLineString"
    POLYGON = "Polygon"
    MULTI_POLYGON = "MultiPolygon"
    GEOMETRY_COLLECTION = "GeometryCollection"
    NULL = "Null"  # the file had no geometry for this feature
    UNKNOWN = "Unknown"  # a type we don't recognise (e.g. LinearRing)

    @classmethod
    def from_geom_type(cls, geom_type: str) -> "GeometryKind":
        """Map a Shapely `geom_type` string to a kind; anything else is UNKNOWN."""
        known = {
            cls.POINT,
            cls.MULTI_POINT,
            cls.LINE_STRING,
            cls.MULTI_LINE_STRING,
            cls.POLYGON,
            cls.MULTI_POLYGON,
            cls.GEOMETRY_COLLECTION,
        }
        try:
            kind = cls(geom_type)
        except ValueError:
            return cls.UNKNOWN
        return kind if kind in known else cls.UNKNOWN