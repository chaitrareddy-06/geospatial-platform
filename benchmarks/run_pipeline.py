"""Runs ONE zipped Shapefile through parse + process and measures it.

Meant to be started in a fresh process per dataset (see run_all.py), because
peak memory is a process-wide high-water mark. Prints one JSON line.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from app.services.dataset_processing import process_dataset
from app.services.shapefile_parser import parse_shapefile_zip

MB = 1024 * 1024


def _peak_mb(proc: psutil.Process) -> float:
    """Peak working set on Windows; falls back to current RSS elsewhere."""
    info = proc.memory_info()
    peak = getattr(info, "peak_wset", None)
    return (peak if peak is not None else info.rss) / MB


def _count(result: Any) -> int:
    value = result.feature_count
    return int(value() if callable(value) else value)


def run_once(zip_path: Path) -> dict[str, Any]:
    """Process one zip and return timings, throughput, CPU and memory."""
    content = zip_path.read_bytes()  # raises FileNotFoundError if missing
    proc = psutil.Process()
    baseline_mb = proc.memory_info().rss / MB

    cpu_start = time.process_time()
    t0 = time.perf_counter()
    datasets = parse_shapefile_zip(content, zip_path.name)
    t1 = time.perf_counter()
    results = [process_dataset(dataset) for dataset in datasets]
    t2 = time.perf_counter()
    cpu_seconds = time.process_time() - cpu_start

    features = sum(_count(result) for result in results)
    total = t2 - t0
    return {
        "file": zip_path.name,
        "zip_kb": round(len(content) / 1024, 1),
        "features": features,
        "parse_s": round(t1 - t0, 3),
        "process_s": round(t2 - t1, 3),
        "total_s": round(total, 3),
        "features_per_s": round(features / total, 1) if total > 0 else 0.0,
        "cpu_s": round(cpu_seconds, 3),
        "cpu_percent_of_one_core": round(100 * cpu_seconds / total, 1) if total > 0 else 0.0,
        "baseline_mb": round(baseline_mb, 1),
        "peak_mb": round(_peak_mb(proc), 1),
    }


def main() -> None:
    print(json.dumps(run_once(Path(sys.argv[1]))))


if __name__ == "__main__":
    main()