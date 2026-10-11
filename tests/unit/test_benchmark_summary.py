"""summarise() must report the median, not the mean or the best run."""

from __future__ import annotations

from benchmarks.run_all import summarise


def _run(total, per_s=100.0, peak=120.0):
    return {"features": 10, "total_s": total, "features_per_s": per_s, "peak_mb": peak}


def test_median_ignores_one_outlier():
    summary = summarise([_run(1.0), _run(1.1), _run(9.0)])
    assert summary["total_s_median"] == 1.1


def test_min_max_and_repeats():
    summary = summarise([_run(2.0), _run(1.0), _run(3.0)])
    assert (summary["total_s_min"], summary["total_s_max"], summary["repeats"]) == (1.0, 3.0, 3)


def test_peak_memory_is_the_maximum():
    summary = summarise([_run(1.0, peak=100.0), _run(1.0, peak=140.0)])
    assert summary["peak_mb_max"] == 140.0