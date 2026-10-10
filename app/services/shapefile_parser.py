"""Parse a zipped Shapefile into ParsedDatasets.

Extraction is delegated to the safe extractor (Step 5). Reading uses
GeoPandas with the pyogrio engine. One ZIP may hold several Shapefiles,
so a list of datasets is returned.
"""

import math
from datetime import date, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyogrio.errors import DataLayerError, DataSourceError, FieldError, GeometryError

from app.core.exceptions import CorruptShapefileError
from app.domain.entities.dataset import ParsedDataset
from app.domain.entities.feature import Feature
from app.domain.enums.file_kind import FileKind
from app.services.zip_extraction import ExtractedShapefile, extract_shapefiles

_READ_ERRORS = (DataSourceError, DataLayerError, GeometryError, FieldError, ValueError, OSError)


def _to_python(value: Any) -> Any:
    """Convert NumPy/pandas values to plain, JSON-friendly Python values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass  # not a scalar; fall through
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (datetime, date)):  # pd.Timestamp is a datetime
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _read_layer(extracted: ExtractedShapefile) -> gpd.GeoDataFrame:
    try:
        return gpd.read_file(extracted.shp_path, engine="pyogrio")
    except _READ_ERRORS as exc:
        raise CorruptShapefileError(
            details={"shapefile": extracted.source_stem, "reason": str(exc)}
        ) from exc


def _crs_text(gdf: gpd.GeoDataFrame, has_prj: bool, label: str) -> tuple[str | None, list[str]]:
    if not has_prj:
        return None, [f"{label}: no .prj file, so the CRS is unknown"]
    crs = gdf.crs
    if crs is None:
        return None, [f"{label}: the .prj file could not be interpreted, so the CRS is unknown"]
    epsg = crs.to_epsg()
    return (f"EPSG:{epsg}" if epsg else crs.to_wkt()), []


def _build_dataset(
    extracted: ExtractedShapefile, source_name: str, gdf: gpd.GeoDataFrame
) -> ParsedDataset:
    label = extracted.source_stem
    crs_text, warnings = _crs_text(gdf, extracted.has_prj, label)

    geometries = list(gdf.geometry)
    columns = [c for c in gdf.columns if c != gdf.geometry.name]
    values = {c: gdf[c].tolist() for c in columns}

    features: list[Feature] = []
    for i, geometry in enumerate(geometries):
        props = {c: _to_python(values[c][i]) for c in columns}
        if geometry is None:
            features.append(
                Feature(index=i, geometry=None, properties=props, skip_reason="Feature has no geometry")
            )
        else:
            features.append(Feature(index=i, geometry=geometry, properties=props))

    if not features:
        warnings.append(f"{label}: the Shapefile contains no features")

    return ParsedDataset(
        source_name=source_name,
        source_kind=FileKind.ZIP_SHAPEFILE,
        features=tuple(features),
        crs_text=crs_text,
        warnings=tuple(warnings),
    )


def parse_shapefile_zip(content: bytes, source_name: str = "upload.zip") -> list[ParsedDataset]:
    datasets: list[ParsedDataset] = []
    with extract_shapefiles(content) as shapefiles:
        multiple = len(shapefiles) > 1
        for extracted in shapefiles:
            name = f"{source_name}:{extracted.source_stem}" if multiple else source_name
            datasets.append(_build_dataset(extracted, name, _read_layer(extracted)))
    return datasets