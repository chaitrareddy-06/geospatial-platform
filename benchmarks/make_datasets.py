"""Generates the benchmark datasets into benchmarks/data/ (git-ignored)."""

from __future__ import annotations

from pathlib import Path

from benchmarks.dataset_generator import build_geodataframe, write_shapefile_zip

SIZES = (100, 1_000, 10_000, 100_000)
OUT_DIR = Path("benchmarks") / "data"


def main() -> None:
    for size in SIZES:
        gdf = build_geodataframe(size, kind="polygon")
        path = write_shapefile_zip(gdf, OUT_DIR / f"polygon_{size}.zip")
        print(f"{path}  {path.stat().st_size / 1024:,.0f} KB  ({size:,} features)")


if __name__ == "__main__":
    main()