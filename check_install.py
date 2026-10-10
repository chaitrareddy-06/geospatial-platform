import geopandas
import numpy as np
import pyogrio
import pyproj
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon

print("shapely :", shapely.__version__)
print("pyproj  :", pyproj.__version__)
print("geopandas:", geopandas.__version__)
print("pyogrio :", pyogrio.__version__)
print("GDAL    :", pyogrio.__gdal_version_string__)

# Small square near Hyderabad, in lon/lat degrees (EPSG:4326)
square = Polygon([(78.0, 17.0), (78.01, 17.0), (78.01, 17.01), (78.0, 17.01)])

# Area in degrees is meaningless. This is the mistake we must never make.
print("Area in degrees (WRONG):", square.area)

# Transformer from EPSG:4326 to UTM zone 44N (EPSG:32644).
# always_xy=True means input order is (lon, lat), not (lat, lon).
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)


def reproject_coords(coords: np.ndarray) -> np.ndarray:
    """Take an (N, 2) array of lon/lat, return an (N, 2) array of x/y in metres."""
    x, y = to_utm.transform(coords[:, 0], coords[:, 1])
    return np.column_stack((x, y))


# shapely.transform applies the function to every coordinate of the geometry
square_utm = shapely.transform(square, reproject_coords)
print("Area in UTM m2 (RIGHT) :", round(square_utm.area, 2))