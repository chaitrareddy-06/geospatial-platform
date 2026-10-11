"""Prometheus metrics.

The Metrics class takes plain numbers (counts, durations), never service or
domain objects, so the pure services stay free of ``prometheus_client``. A small
adapter (``observer.py``) reads the result objects and calls these methods.

Every Metrics instance owns its own registry. Tests create their own instance
and cannot disturb each other; the app uses the single shared one from
``get_metrics()``.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from functools import lru_cache

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

UPLOAD_SIZE_BUCKETS = (
    1_000, 10_000, 100_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000, 100_000_000,
)
DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)
API_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

UNKNOWN_REASON = "unknown"
ERROR_STATUS_FROM = 400

_FAMILIES = {
    "polygon": "polygon",
    "multipolygon": "polygon",
    "linestring": "linestring",
    "multilinestring": "linestring",
    "point": "point",
    "multipoint": "point",
    "geometrycollection": "collection",
}


def family_of(kind: object) -> str | None:
    """Map a geometry kind name to polygon / linestring / point / collection.

    Case and underscores are ignored, so "MultiPolygon" and "MULTI_POLYGON"
    both give "polygon". Returns None for kinds with no family (null, unknown).
    """
    key = str(kind).lower().replace("_", "").replace(" ", "")
    return _FAMILIES.get(key)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        reg = self.registry

        # Uploads and jobs
        self.files_uploaded = Counter(
            "files_uploaded_total", "Files accepted for processing.", registry=reg
        )
        self.upload_size = Histogram(
            "upload_size_bytes",
            "Size of accepted uploads in bytes.",
            buckets=UPLOAD_SIZE_BUCKETS,
            registry=reg,
        )
        self.largest_upload = Gauge(
            "largest_upload_size_bytes",
            "Largest accepted upload since the process started.",
            registry=reg,
        )
        self.jobs_total = Counter(
            "processing_jobs_total", "Processing jobs that finished.", registry=reg
        )
        self.jobs_success = Counter(
            "processing_jobs_success_total",
            "Processing jobs that completed.",
            registry=reg,
        )
        self.jobs_failed = Counter(
            "processing_jobs_failed_total",
            "Processing jobs that failed, by reason.",
            ["reason"],
            registry=reg,
        )
        self.processing_duration = Histogram(
            "processing_duration_seconds",
            "Wall-clock time of one processing job.",
            buckets=DURATION_BUCKETS,
            registry=reg,
        )

        # Features and geometry
        self.features_processed = Counter(
            "features_processed_total", "Features seen by the pipeline.", registry=reg
        )
        self.geometry_features = Counter(
            "geometry_features_total",
            "Features by geometry kind (distribution).",
            ["kind"],
            registry=reg,
        )
        self.polygon_features = Counter(
            "polygon_features_total", "Polygon and MultiPolygon features.", registry=reg
        )
        self.linestring_features = Counter(
            "linestring_features_total",
            "LineString and MultiLineString features.",
            registry=reg,
        )
        self.point_features = Counter(
            "point_features_total", "Point and MultiPoint features.", registry=reg
        )
        self.geometry_collections = Counter(
            "geometry_collections_total", "GeometryCollection features.", registry=reg
        )
        self.area_calculations = Counter(
            "area_calculations_total", "Area calculations performed.", registry=reg
        )
        self.length_calculations = Counter(
            "length_calculations_total", "Length calculations performed.", registry=reg
        )
        self.measurement_duration = Histogram(
            "measurement_duration_seconds",
            "Time to process one dataset (validate, project, measure).",
            buckets=DURATION_BUCKETS,
            registry=reg,
        )

        # Validation
        self.validation_failures = Counter(
            "validation_failures_total",
            "Features skipped or failed, by stable reason code.",
            ["type"],
            registry=reg,
        )
        self.invalid_geometries = Counter(
            "invalid_geometries_total", "Geometries that were invalid.", registry=reg
        )
        self.repaired_geometries = Counter(
            "repaired_geometries_total",
            "Invalid geometries repaired with make_valid.",
            registry=reg,
        )

        # CRS decisions
        self.crs_transformations = Counter(
            "crs_transformations_total",
            "Datasets that were reprojected before measuring.",
            registry=reg,
        )
        self.crs_resolutions = Counter(
            "crs_resolution_total",
            "CRS decisions made, by strategy.",
            ["strategy"],
            registry=reg,
        )
        self.crs_resolution_failures = Counter(
            "crs_resolution_failures_total",
            "CRS decisions that failed, by reason.",
            ["reason"],
            registry=reg,
        )
        self.utm_selections = Counter(
            "utm_selection_total", "Datasets measured in a UTM zone.", registry=reg
        )
        self.equal_area_selections = Counter(
            "equal_area_selection_total",
            "Datasets measured in an equal-area projection.",
            registry=reg,
        )

        # Workload (set from the job runner's statistics)
        self.active_jobs = Gauge(
            "active_jobs", "Jobs running right now.", registry=reg
        )
        self.queue_size = Gauge(
            "queue_size", "Jobs waiting for a worker.", registry=reg
        )

        # HTTP API (fed by the request middleware)
        self.api_requests = Counter(
            "api_request_total",
            "HTTP requests, by method, route template and status code.",
            ["method", "path", "status"],
            registry=reg,
        )
        self.api_errors = Counter(
            "api_error_total",
            "HTTP responses with status 400 or higher.",
            ["method", "path", "status"],
            registry=reg,
        )
        self.api_request_duration = Histogram(
            "api_request_duration_seconds",
            "Time to answer one HTTP request.",
            ["method", "path"],
            buckets=API_LATENCY_BUCKETS,
            registry=reg,
        )

        self._largest = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------

    def record_upload(self, size_bytes: int) -> None:
        self.files_uploaded.inc()
        self.upload_size.observe(size_bytes)
        with self._lock:
            if size_bytes > self._largest:
                self._largest = size_bytes
                self.largest_upload.set(size_bytes)

    def record_job(
        self,
        *,
        success: bool,
        reason: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        self.jobs_total.inc()
        if success:
            self.jobs_success.inc()
        else:
            self.jobs_failed.labels(reason=reason or UNKNOWN_REASON).inc()
        if duration_seconds is not None:
            self.processing_duration.observe(duration_seconds)

    def record_dataset(
        self,
        *,
        kind_counts: Mapping[str, int],
        measured: int,
        skipped: int,
        failed: int,
        area_calculations: int,
        length_calculations: int,
        duration_seconds: float,
        crs_strategy: str,
        reprojected: bool,
        repaired: int,
        invalid: int,
        skip_reasons: Mapping[str, int],
    ) -> None:
        self.features_processed.inc(measured + skipped + failed)
        for kind, count in kind_counts.items():
            self.geometry_features.labels(kind=str(kind)).inc(count)
            family = family_of(kind)
            if family == "polygon":
                self.polygon_features.inc(count)
            elif family == "linestring":
                self.linestring_features.inc(count)
            elif family == "point":
                self.point_features.inc(count)
            elif family == "collection":
                self.geometry_collections.inc(count)

        self.area_calculations.inc(area_calculations)
        self.length_calculations.inc(length_calculations)
        self.measurement_duration.observe(duration_seconds)

        self.repaired_geometries.inc(repaired)
        self.invalid_geometries.inc(invalid)
        for code, count in skip_reasons.items():
            self.validation_failures.labels(type=str(code)).inc(count)

        self.crs_resolutions.labels(strategy=crs_strategy).inc()
        if crs_strategy == "utm":
            self.utm_selections.inc()
        elif crs_strategy == "laea":
            self.equal_area_selections.inc()
        if reprojected:
            self.crs_transformations.inc()

    def record_crs_failure(self, reason: str) -> None:
        self.crs_resolution_failures.labels(reason=reason).inc()

    def set_workload(self, *, queued: int, active: int) -> None:
        self.queue_size.set(queued)
        self.active_jobs.set(active)

    def record_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """One HTTP request. ``path`` must be a route template, not a raw URL."""
        status = str(status_code)
        self.api_requests.labels(method=method, path=path, status=status).inc()
        self.api_request_duration.labels(method=method, path=path).observe(
            duration_seconds
        )
        if status_code >= ERROR_STATUS_FROM:
            self.api_errors.labels(method=method, path=path, status=status).inc()

    # ------------------------------------------------------------------

    content_type = CONTENT_TYPE_LATEST

    def render(self) -> bytes:
        """The text Prometheus scrapes."""
        return generate_latest(self.registry)


@lru_cache
def get_metrics() -> Metrics:
    """The one Metrics object for the whole process."""
    return Metrics()