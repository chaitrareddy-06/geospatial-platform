"""Shared test fixtures: sample files and a service factory."""

import io
import itertools
import warnings
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import box

from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService

KML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>plot</name>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        78.40,17.40,0 78.41,17.40,0 78.41,17.41,0 78.40,17.41,0 78.40,17.40,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
    <Placemark>
      <name>road</name>
      <LineString><coordinates>78.40,17.40,0 78.41,17.41,0</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>gate</name>
      <Point><coordinates>78.405,17.405,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""


@pytest.fixture
def kml_bytes() -> bytes:
    """A valid KML with one polygon, one line and one point (3 features)."""
    return KML_SAMPLE.encode("utf-8")


@pytest.fixture
def shapefile_zip(tmp_path):
    """Factory: build a zipped Shapefile with two polygons.

    Call ``shapefile_zip()`` for EPSG:4326, or ``shapefile_zip(None)`` for a
    Shapefile with no CRS (no .prj file).
    """
    counter = itertools.count()

    def build(crs: str | None = "EPSG:4326") -> bytes:
        # Folder names must not contain the CRS text: ":" is illegal on Windows.
        folder = tmp_path / f"shp_{next(counter)}"
        folder.mkdir()
        frame = gpd.GeoDataFrame(
            {"name": ["a", "b"]},
            geometry=[box(78.40, 17.40, 78.41, 17.41), box(78.42, 17.40, 78.43, 17.41)],
            crs=crs,
        )
        with warnings.catch_warnings():
            # Writing a Shapefile without a CRS is the whole point of crs=None,
            # so the library's "'crs' was not provided" warning is expected here.
            warnings.filterwarnings("ignore", message="'crs' was not provided")
            frame.to_file(folder / "layer.shp", driver="ESRI Shapefile")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.iterdir()):
                archive.write(path, arcname=path.name)
        return buffer.getvalue()

    return build


@pytest.fixture
def make_service():
    """Factory: a FileService on fresh in-memory repositories."""

    def build(
        *,
        assume_wgs84_if_missing: bool = False,
        max_upload_size_bytes: int = 50 * 1024 * 1024,
        repository: InMemoryFileRepository | None = None,
        feature_repository: InMemoryFeatureResultRepository | None = None,
    ) -> FileService:
        return FileService(
            repository if repository is not None else InMemoryFileRepository(),
            feature_repository=(
                feature_repository
                if feature_repository is not None
                else InMemoryFeatureResultRepository()
            ),
            assume_wgs84_if_missing=assume_wgs84_if_missing,
            max_utm_offset_deg=4.0,
            max_upload_size_bytes=max_upload_size_bytes,
        )

    return build