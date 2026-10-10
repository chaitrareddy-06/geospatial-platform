"""Print how wrong a UTM zone gets as data moves away from its centre line.

Run from the project root:   python scripts/crs_error_table.py

For UTM zone 44 (centre line 81 E) we place a tiny 0.01 deg square at several
latitudes and offsets, measure its area in UTM, and compare with the geodesic
(ellipsoid) area. Output is a Markdown table for the README.
All squares are synthetic; the numbers come from running this script.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import shapely  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely.geometry import box  # noqa: E402

from app.services.geodesic import geodesic_measure  # noqa: E402

ZONE_44_CENTRE_LON = 81.0
UTM_44N = "EPSG:32644"
SIZE_DEG = 0.01
LATITUDES = (0.0, 17.0, 40.0)
OFFSETS_DEG = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)

_TO_UTM = Transformer.from_crs("EPSG:4326", UTM_44N, always_xy=True)


def _utm_area(geometry) -> float:
    def _apply(coords):
        x, y = _TO_UTM.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    return float(shapely.transform(geometry, _apply).area)


def main() -> None:
    print(f"UTM zone 44N area error vs geodesic, {SIZE_DEG} deg squares (synthetic)")
    print()
    header = "| latitude | " + " | ".join(f"{o:.0f} deg" for o in OFFSETS_DEG) + " |"
    print(header)
    print("|" + "---|" * (len(OFFSETS_DEG) + 1))
    for lat in LATITUDES:
        cells = []
        for offset in OFFSETS_DEG:
            lon = ZONE_44_CENTRE_LON + offset
            square = box(lon, lat, lon + SIZE_DEG, lat + SIZE_DEG)
            projected = _utm_area(square)
            geodesic = geodesic_measure(square).area_m2
            diff = (projected - geodesic) / geodesic * 100.0
            cells.append(f"{diff:+.3f}%")
        print(f"| {lat:.0f} N | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()