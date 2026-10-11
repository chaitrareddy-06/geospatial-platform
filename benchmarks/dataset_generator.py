"""Builds synthetic, reproducible datasets for the benchmark suite.

Everything here is synthetic: random shapes around Hyderabad in EPSG:4326, with
a fixed seed so every run measures identical data. A Shapefile holds exactly
one geometry type, so each dataset is one `kind`.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

KINDS = ("polygon", "line", "point")
LON_MIN, LON_MAX = 78.20, 78.70
LAT_MIN, LAT_MAX = 17.20, 17.60


def build_geodataframe(
    n_features: int, kind: str = "polygon", seed: int = 42
) -> gpd.GeoDataFrame:
    """Return n_features random, valid features of one geometry kind."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    if n_features < 1:
        raise ValueError("n_features must be at least 1")

    rng = np.random.default_rng(seed)
    lon = rng.uniform(LON_MIN, LON_MAX, n_features)
    lat = rng.uniform(LAT_MIN, LAT_MAX, n_features)

    if kind == "polygon":
        width = rng.uniform(0.0005, 0.003, n_features)
        height = rng.uniform(0.0005, 0.003, n_features)
        geoms = shapely.box(lon, lat, lon + width, lat + height)
    elif kind == "line":
        start = np.stack([lon, lat], axis=1)[:, None, :]
        steps = rng.uniform(-0.002, 0.002, (n_features, 3, 2))
        coords = np.cumsum(np.concatenate([start, steps], axis=1), axis=1)
        geoms = shapely.linestrings(coords)
    else:
        geoms = shapely.points(lon, lat)

    return gpd.GeoDataFrame(
        {
            "feat_id": np.arange(n_features),
            "name": [f"feature_{i}" for i in range(n_features)],
            "category": rng.choice(["a", "b", "c"], n_features),
        },
        geometry=geoms,
        crs="EPSG:4326",
    )


def write_shapefile_zip(gdf: gpd.GeoDataFrame, zip_path: Path) -> Path:
    """Write gdf as a Shapefile and zip its parts (.shp .shx .dbf .prj ...)."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        gdf.to_file(Path(tmp) / "benchmark.shp", driver="ESRI Shapefile")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for part in sorted(Path(tmp).iterdir()):
                archive.write(part, arcname=part.name)
    return zip_path