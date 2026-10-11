"""Runs every benchmark dataset several times, one fresh process per run.

Reports median, min and max so one noisy run cannot mislead. Writes
benchmarks/results/pipeline.json so the README numbers trace to a file.
"""

from __future__ import annotations

import json
import platform
import statistics
import subprocess
import sys
from pathlib import Path

import psutil

from benchmarks.make_datasets import OUT_DIR, SIZES

RESULTS = Path("benchmarks") / "results" / "pipeline.json"
DEFAULT_REPEATS = 5


def machine_info() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
    }


def run_dataset(path: Path) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, "-m", "benchmarks.run_pipeline", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{path.name} failed:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])  # last line is the JSON


def summarise(runs: list[dict[str, object]]) -> dict[str, object]:
    """Median, min and max of the numbers that matter, over repeated runs."""
    def column(key: str) -> list[float]:
        return [float(r[key]) for r in runs]  # type: ignore[arg-type]

    total = column("total_s")
    return {
        "features": runs[0]["features"],
        "repeats": len(runs),
        "total_s_median": round(statistics.median(total), 3),
        "total_s_min": min(total),
        "total_s_max": max(total),
        "features_per_s_median": round(statistics.median(column("features_per_s")), 1),
        "peak_mb_max": max(column("peak_mb")),
        "all_runs": runs,
    }


def main() -> None:
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REPEATS
    paths = [OUT_DIR / f"polygon_{size}.zip" for size in SIZES]
    if [p for p in paths if not p.exists()]:
        sys.exit("Missing datasets. Run: python -m benchmarks.make_datasets")

    info = machine_info()
    summaries = [summarise([run_dataset(p) for _ in range(repeats)]) for p in paths]

    print(f"Machine: {info}   repeats per size: {repeats}")
    print(f"{'features':>9} {'median_s':>9} {'min_s':>8} {'max_s':>8} {'feat/s(med)':>12} {'peak_MB':>8}")
    for s in summaries:
        print(f"{s['features']:>9,} {s['total_s_median']:>9} {s['total_s_min']:>8} "
              f"{s['total_s_max']:>8} {s['features_per_s_median']:>12,} {s['peak_mb_max']:>8}")

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"machine": info, "repeats": repeats, "sizes": summaries}, indent=2))
    print(f"Saved {RESULTS}")


if __name__ == "__main__":
    main()