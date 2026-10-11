"""POST /files/ tells the client where to poll, via the Location header."""

KML_TYPE = "application/vnd.google-earth.kml+xml"


def _upload(client, path, kml_bytes):
    return client.post(path, files={"file": ("survey.kml", kml_bytes, KML_TYPE)})


def test_location_header_points_at_the_v1_record(client, kml_bytes):
    response = _upload(client, "/api/v1/files/", kml_bytes)

    assert response.status_code == 202
    assert response.headers["Location"] == f"/api/v1/files/{response.json()['id']}/"


def test_location_header_on_the_assignment_alias_uses_the_alias_path(client, kml_bytes):
    response = _upload(client, "/api/files/", kml_bytes)

    assert response.status_code == 202
    assert response.headers["Location"] == f"/api/files/{response.json()['id']}/"


def test_following_the_location_header_returns_the_same_file(client, kml_bytes):
    posted = _upload(client, "/api/v1/files/", kml_bytes)

    followed = client.get(posted.headers["Location"])

    assert followed.status_code == 200
    assert followed.json()["id"] == posted.json()["id"]