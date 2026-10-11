"""The runner must report real, internally consistent numbers."""

from __future__ import annotations

import pytest

from benchmarks.dataset_generator import build_geodataframe, write_shapefile_zip
from benchmarks.run_pipeline import run_once


@pytest.fixture
def small_zip(tmp_path):
    return write_shapefile_zip(build_geodataframe(100), tmp_path / "small.zip")


def test_reports_the_real_feature_count(small_zip):
    assert run_once(small_zip)["features"] == 100


def test_numbers_are_positive_and_consistent(small_zip):
    result = run_once(small_zip)
    assert result["total_s"] > 0
    assert result["features_per_s"] > 0
    assert result["peak_mb"] >= result["baseline_mb"] > 0
    assert result["total_s"] >= result["parse_s"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_once(tmp_path / "nope.zip")