from app.core.exceptions import (
    CRSResolutionError,
    DuplicateFileError,
    EmptyFileError,
    FileTooLargeError,
    ResourceNotFoundError,
    UnsupportedFileTypeError,
)


class NoopRunner:
    """A runner that never runs the job, so the file stays QUEUED."""

    def submit(self, file_id: str, content: bytes) -> None:
        return None

    def shutdown(self, wait: bool = True) -> None:
        return None


def _upload(client, name, content, url="/api/v1/files/"):
    return client.post(url, files={"file": (name, content, "application/octet-stream")})


def _upload_and_fetch(client, name, content):
    """Upload (expects 202), then read the record back after the job has run."""
    created = _upload(client, name, content)
    assert created.status_code == 202
    return client.get(f"/api/v1/files/{created.json()['id']}/").json()


def test_upload_returns_202_and_a_queued_record(client, kml_bytes):
    response = _upload(client, "survey.kml", kml_bytes)
    assert response.status_code == 202
    body = response.json()
    assert body["id"]
    assert body["filename"] == "survey.kml"
    assert body["status"] == "QUEUED"
    assert body["error"] is None


def test_upload_kml_completes_in_the_background(client, kml_bytes):
    body = _upload_and_fetch(client, "survey.kml", kml_bytes)
    assert body["filename"] == "survey.kml"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["status"] == "COMPLETED"
    assert body["error"] is None


def test_file_stays_queued_until_a_worker_runs_it(make_client, make_service, kml_bytes):
    client = make_client(make_service(), runner=NoopRunner())
    created = _upload(client, "survey.kml", kml_bytes).json()
    fetched = client.get(f"/api/v1/files/{created['id']}/").json()
    assert fetched["status"] == "QUEUED"
    assert fetched["feature_count"] == 0


def test_measurements_of_a_queued_file_are_empty_with_its_status(
    make_client, make_service, kml_bytes
):
    client = make_client(make_service(), runner=NoopRunner())
    created = _upload(client, "survey.kml", kml_bytes).json()
    page = client.get(f"/api/v1/files/{created['id']}/measurements/").json()
    assert page["file_status"] == "QUEUED"
    assert page["total"] == 0
    assert page["items"] == []


def test_upload_via_assignment_alias_path(client, kml_bytes):
    response = _upload(client, "survey.kml", kml_bytes, url="/api/files/")
    assert response.status_code == 202
    fetched = client.get(f"/api/files/{response.json()['id']}/").json()
    assert fetched["status"] == "COMPLETED"


def test_get_record_by_id(client, kml_bytes):
    created = _upload(client, "survey.kml", kml_bytes).json()
    response = client.get(f"/api/v1/files/{created['id']}/")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["feature_count"] == 3


def test_get_via_assignment_alias_path(client, kml_bytes):
    created = _upload(client, "survey.kml", kml_bytes).json()
    response = client.get(f"/api/files/{created['id']}/")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_id_returns_404(client):
    response = client.get("/api/v1/files/does-not-exist/")
    assert response.status_code == ResourceNotFoundError.status_code
    assert response.json()["error"]["code"] == ResourceNotFoundError.error_code


def test_duplicate_upload_returns_409_with_existing_id(client, kml_bytes):
    first = _upload(client, "survey.kml", kml_bytes).json()
    response = _upload(client, "again.kml", kml_bytes)
    assert response.status_code == DuplicateFileError.status_code
    error = response.json()["error"]
    assert error["code"] == DuplicateFileError.error_code
    assert error["details"]["existing_id"] == first["id"]


def test_empty_upload_is_rejected(client):
    response = _upload(client, "survey.kml", b"")
    assert response.status_code == EmptyFileError.status_code
    assert response.json()["error"]["code"] == EmptyFileError.error_code


def test_unsupported_extension_returns_415(client):
    response = _upload(client, "notes.txt", b"hello")
    assert response.status_code == UnsupportedFileTypeError.status_code


def test_oversized_upload_returns_413(make_client, make_service, kml_bytes):
    client = make_client(make_service(max_upload_size_bytes=10))
    response = _upload(client, "survey.kml", kml_bytes)
    assert response.status_code == FileTooLargeError.status_code
    assert response.json()["error"]["code"] == FileTooLargeError.error_code


def test_missing_file_field_returns_422(client):
    response = client.post("/api/v1/files/")
    assert response.status_code == 422


def test_upload_zipped_shapefile(client, shapefile_zip):
    body = _upload_and_fetch(client, "parcels.zip", shapefile_zip())
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2


def test_missing_crs_is_reported_as_failed_record(client, shapefile_zip):
    body = _upload_and_fetch(client, "parcels.zip", shapefile_zip(None))
    assert body["status"] == "FAILED"
    assert body["error"]["code"] == CRSResolutionError.error_code
    assert body["error"]["reason"] == "missing_crs"


def test_layer_details_are_returned(client, kml_bytes):
    body = _upload_and_fetch(client, "survey.kml", kml_bytes)
    assert len(body["layers"]) == 1
    layer = body["layers"][0]
    assert layer["crs_strategy"] == "utm"
    assert layer["measured_count"] == 3


def test_alias_routes_are_hidden_from_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/files/" in paths
    assert "/api/files/" not in paths