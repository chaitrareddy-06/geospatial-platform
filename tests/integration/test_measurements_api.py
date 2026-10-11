import pytest

KML_TYPE = "application/vnd.google-earth.kml+xml"


def _upload_kml(client, kml_bytes) -> str:
    response = client.post(
        "/api/v1/files/", files={"file": ("survey.kml", kml_bytes, KML_TYPE)}
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_measurements_lists_all_features(client, kml_bytes):
    file_id = _upload_kml(client, kml_bytes)
    response = client.get(f"/api/v1/files/{file_id}/measurements/")
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == file_id
    assert body["file_status"] == "COMPLETED"
    assert body["total"] == 3
    assert len(body["items"]) == 3

    polygons = [i for i in body["items"] if i["area_m2"] is not None]
    lines = [i for i in body["items"] if i["length_m"] is not None]
    points = [
        i for i in body["items"] if i["area_m2"] is None and i["length_m"] is None
    ]
    assert (len(polygons), len(lines), len(points)) == (1, 1, 1)


def test_polygon_area_is_plausible(client, kml_bytes):
    file_id = _upload_kml(client, kml_bytes)
    items = client.get(f"/api/v1/files/{file_id}/measurements/").json()["items"]
    area = next(i["area_m2"] for i in items if i["area_m2"] is not None)
    # 0.01 x 0.01 degrees at 17.4 N is about 1.17 square kilometres.
    assert 1.0e6 < area < 1.3e6


def test_cross_check_is_present_and_small(client, kml_bytes):
    file_id = _upload_kml(client, kml_bytes)
    items = client.get(f"/api/v1/files/{file_id}/measurements/").json()["items"]
    polygon = next(i for i in items if i["area_m2"] is not None)
    assert polygon["cross_check"] is not None
    assert abs(polygon["cross_check"]["area_diff_pct"]) < 1.0
    assert polygon["length_method"] is None  # polygons have no length


def test_pagination_returns_the_requested_slice(client, kml_bytes):
    file_id = _upload_kml(client, kml_bytes)
    everything = client.get(f"/api/v1/files/{file_id}/measurements/").json()["items"]
    page = client.get(
        f"/api/v1/files/{file_id}/measurements/", params={"limit": 1, "offset": 1}
    ).json()
    assert page["total"] == 3
    assert (page["limit"], page["offset"]) == (1, 1)
    assert page["items"] == [everything[1]]


def test_status_filter(client, kml_bytes):
    file_id = _upload_kml(client, kml_bytes)
    measured = client.get(
        f"/api/v1/files/{file_id}/measurements/", params={"status": "measured"}
    ).json()
    skipped = client.get(
        f"/api/v1/files/{file_id}/measurements/", params={"status": "skipped"}
    ).json()
    assert measured["total"] == 3
    assert skipped["total"] == 0
    assert skipped["items"] == []


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"status": "bogus"}],
)
def test_invalid_query_parameters_return_422(client, kml_bytes, params):
    file_id = _upload_kml(client, kml_bytes)
    response = client.get(f"/api/v1/files/{file_id}/measurements/", params=params)
    assert response.status_code == 422


def test_unknown_file_returns_404(client):
    response = client.get("/api/v1/files/does-not-exist/measurements/")
    assert response.status_code == 404
    assert "error" in response.json()


def test_assignment_alias_path_works(client, kml_bytes):
    file_id = _upload_kml(client, kml_bytes)
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    assert response.json()["total"] == 3


def test_failed_file_gives_an_empty_page_with_its_status(client, shapefile_zip):
    response = client.post(
        "/api/v1/files/",
        files={"file": ("nocrs.zip", shapefile_zip(crs=None), "application/zip")},
    )
    file_id = response.json()["id"]
    assert response.json()["status"] == "FAILED"

    page = client.get(f"/api/v1/files/{file_id}/measurements/").json()
    assert page["file_status"] == "FAILED"
    assert page["total"] == 0
    assert page["items"] == []


def test_shapefile_attributes_are_returned(client, shapefile_zip):
    response = client.post(
        "/api/v1/files/",
        files={"file": ("layer.zip", shapefile_zip(), "application/zip")},
    )
    file_id = response.json()["id"]
    page = client.get(f"/api/v1/files/{file_id}/measurements/").json()
    assert page["total"] == 2
    assert {i["properties"]["name"] for i in page["items"]} == {"a", "b"}
    assert all(i["layer"] for i in page["items"])