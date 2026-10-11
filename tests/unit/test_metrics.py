"""The Metrics class: plain numbers in, Prometheus counters out."""

import pytest

from app.infrastructure.metrics.registry import Metrics, family_of


def value(metrics, name, labels=None):
    return metrics.registry.get_sample_value(name, labels or {})


def dataset_args(**overrides):
    args = {
        "kind_counts": {
            "Polygon": 3,
            "MultiPolygon": 1,
            "LineString": 2,
            "Point": 1,
            "GeometryCollection": 1,
        },
        "measured": 6,
        "skipped": 1,
        "failed": 0,
        "area_calculations": 4,
        "length_calculations": 2,
        "duration_seconds": 0.5,
        "crs_strategy": "utm",
        "reprojected": True,
        "repaired": 1,
        "invalid": 0,
        "skip_reasons": {"empty_geometry": 1},
    }
    args.update(overrides)
    return args


def test_record_upload_counts_and_observes_size():
    m = Metrics()

    m.record_upload(2_000)

    assert value(m, "files_uploaded_total") == 1
    assert value(m, "upload_size_bytes_count") == 1
    assert value(m, "upload_size_bytes_sum") == 2_000


def test_largest_upload_gauge_keeps_the_maximum():
    m = Metrics()

    m.record_upload(100)
    m.record_upload(50)
    assert value(m, "largest_upload_size_bytes") == 100

    m.record_upload(200)
    assert value(m, "largest_upload_size_bytes") == 200


def test_record_job_success():
    m = Metrics()

    m.record_job(success=True, duration_seconds=2.0)

    assert value(m, "processing_jobs_total") == 1
    assert value(m, "processing_jobs_success_total") == 1
    assert value(m, "processing_duration_seconds_count") == 1
    assert value(m, "processing_duration_seconds_sum") == 2.0


def test_record_job_failure_uses_the_reason_label():
    m = Metrics()

    m.record_job(success=False, reason="invalid_crs")
    m.record_job(success=False)

    assert value(m, "processing_jobs_total") == 2
    assert value(m, "processing_jobs_success_total") == 0
    assert value(m, "processing_jobs_failed_total", {"reason": "invalid_crs"}) == 1
    assert value(m, "processing_jobs_failed_total", {"reason": "unknown"}) == 1


def test_record_dataset_counts_features_and_geometry_families():
    m = Metrics()

    m.record_dataset(**dataset_args())

    assert value(m, "features_processed_total") == 7
    assert value(m, "polygon_features_total") == 4
    assert value(m, "linestring_features_total") == 2
    assert value(m, "point_features_total") == 1
    assert value(m, "geometry_collections_total") == 1
    assert value(m, "geometry_features_total", {"kind": "Polygon"}) == 3


def test_record_dataset_calculations_validation_and_timing():
    m = Metrics()

    m.record_dataset(**dataset_args(invalid=2))

    assert value(m, "area_calculations_total") == 4
    assert value(m, "length_calculations_total") == 2
    assert value(m, "repaired_geometries_total") == 1
    assert value(m, "invalid_geometries_total") == 2
    assert value(m, "validation_failures_total", {"type": "empty_geometry"}) == 1
    assert value(m, "measurement_duration_seconds_count") == 1
    assert value(m, "measurement_duration_seconds_sum") == 0.5


def test_crs_strategy_counters():
    m = Metrics()

    m.record_dataset(**dataset_args(crs_strategy="utm", reprojected=True))
    assert value(m, "utm_selection_total") == 1
    assert value(m, "equal_area_selection_total") == 0
    assert value(m, "crs_transformations_total") == 1
    assert value(m, "crs_resolution_total", {"strategy": "utm"}) == 1

    m.record_dataset(**dataset_args(crs_strategy="laea", reprojected=True))
    m.record_dataset(**dataset_args(crs_strategy="native_projected", reprojected=False))

    assert value(m, "equal_area_selection_total") == 1
    assert value(m, "utm_selection_total") == 1
    assert value(m, "crs_transformations_total") == 2
    assert value(m, "crs_resolution_total", {"strategy": "native_projected"}) == 1


def test_crs_failure_counter():
    m = Metrics()

    m.record_crs_failure("missing_crs")
    m.record_crs_failure("missing_crs")

    assert value(m, "crs_resolution_failures_total", {"reason": "missing_crs"}) == 2


def test_set_workload_sets_both_gauges():
    m = Metrics()

    m.set_workload(queued=3, active=1)

    assert value(m, "queue_size") == 3
    assert value(m, "active_jobs") == 1


def test_render_contains_the_metric_names():
    text = Metrics().render().decode()

    for name in ("files_uploaded_total", "active_jobs", "queue_size"):
        assert name in text


def test_instances_do_not_share_state():
    first = Metrics()
    second = Metrics()

    first.record_upload(10)

    assert value(first, "files_uploaded_total") == 1
    assert value(second, "files_uploaded_total") == 0


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("MULTI_POLYGON", "polygon"),
        ("MultiPolygon", "polygon"),
        ("LineString", "linestring"),
        ("multi_point", "point"),
        ("GeometryCollection", "collection"),
    ],
)
def test_family_of_ignores_case_and_underscores(kind, expected):
    assert family_of(kind) == expected
    