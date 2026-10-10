from app.core.exceptions import (
    CRSResolutionError,
    DuplicateFileError,
    EmptyFileError,
    FileTooLargeError,
    ResourceNotFoundError,
    UnsupportedFileTypeError,
)


def _upload(client, name, content, url="/api/v1/files/"):
    return client.post(url, files={"file": (name, content, "application/octet-stream")})


def test_upload_kml_returns_completed_record(client, kml_bytes):
    response = _upload(client, "survey.kml", kml_bytes)
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["filename"] == "survey.kml"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["status"] == "COMPLETED"
    assert body["error"] is None


def test_upload_via_assignment_alias_path(client, kml_bytes):
    response = _upload(client, "survey.kml", kml_bytes, url="/api/files/")
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"


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
    response = _upload(client, "parcels.zip", shapefile_zip())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2


def test_missing_crs_is_reported_as_failed_record(client, shapefile_zip):
    response = _upload(client, "parcels.zip", shapefile_zip(None))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error"]["code"] == CRSResolutionError.error_code
    assert body["error"]["reason"] == "missing_crs"


def test_layer_details_are_returned(client, kml_bytes):
    body = _upload(client, "survey.kml", kml_bytes).json()
    assert len(body["layers"]) == 1
    layer = body["layers"][0]
    assert layer["crs_strategy"] == "utm"
    assert layer["measured_count"] == 3


def test_alias_routes_are_hidden_from_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/files/" in paths
    assert "/api/files/" not in paths