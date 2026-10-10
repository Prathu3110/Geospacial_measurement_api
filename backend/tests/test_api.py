import io
import zipfile

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Feature, UploadedFile
from tests.test_readers import KML


def upload(client, name, content):
    return client.post("/api/files/", files={"file": (name, content)})


def test_health_reports_postgis(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["postgis"].startswith("3.")


def test_kml_upload_is_processed_and_measured(client):
    response = upload(client, "survey.kml", KML.encode())
    assert response.status_code == 202
    assert response.json()["status"] == "PENDING"
    file_id = response.json()["id"]

    # TestClient runs background tasks before returning, so processing has finished here.
    info = client.get(f"/api/files/{file_id}/").json()
    assert info["filename"] == "survey.kml"
    assert info["status"] == "COMPLETED"
    assert info["crs"] == "EPSG:4326"
    assert info["feature_count"] == 3

    page = client.get(f"/api/files/{file_id}/measurements/").json()
    assert page["total"] == 3
    pit, road, marker = page["items"]

    assert pit["geometry_type"] == "Polygon"
    assert pit["measurement_crs"] == "EPSG:32643"
    assert pit["area_ha"] == pytest.approx(pit["area_m2"] / 10_000)
    assert pit["properties"] == {"Name": "Pit A", "owner": "Client X", "layer": "Pits"}
    assert road["length_km"] == pytest.approx(road["length_m"] / 1_000)
    assert marker["reason"] == "no measurement for Point"
    assert marker["area_m2"] is None and marker["length_m"] is None


def test_area_matches_postgis_geography_area(client):
    file_id = upload(client, "survey.kml", KML.encode()).json()["id"]
    [pit] = [
        i
        for i in client.get(f"/api/files/{file_id}/measurements/").json()["items"]
        if i["geometry_type"] == "Polygon"
    ]

    with SessionLocal() as session:
        # PostGIS computes area on the ellipsoid when cast to geography: an independent check.
        postgis_area = session.scalar(
            select(func.ST_Area(func.geography(Feature.geometry))).where(
                Feature.feature_index == pit["feature_index"]
            )
        )
    assert pit["area_m2"] == pytest.approx(postgis_area, rel=2e-3)


def test_features_endpoint_returns_geojson(client):
    file_id = upload(client, "survey.kml", KML.encode()).json()["id"]

    collection = client.get(f"/api/files/{file_id}/features/").json()

    assert collection["type"] == "FeatureCollection"
    assert [f["geometry"]["type"] for f in collection["features"]] == [
        "Polygon",
        "LineString",
        "Point",
    ]
    # Stored in 2D: the KML altitude is dropped.
    assert collection["features"][1]["geometry"]["coordinates"][0] == [77.58, 12.96]


def test_shapefile_without_prj_fails_with_reason(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("pits.shp", b"")
        zf.writestr("pits.shx", b"")
        zf.writestr("pits.dbf", b"")
    file_id = upload(client, "pits.zip", buffer.getvalue()).json()["id"]

    info = client.get(f"/api/files/{file_id}/").json()

    assert info["status"] == "FAILED"
    assert "missing required parts: .prj" in info["error"]
    assert client.get(f"/api/files/{file_id}/measurements/").status_code == 409


def test_wrong_extension_is_rejected_before_storing(client):
    response = upload(client, "survey.geojson", b"{}")

    assert response.status_code == 400
    with SessionLocal() as session:
        assert session.scalar(select(func.count(UploadedFile.id))) == 0


def test_unknown_file_is_404(client):
    response = client.get("/api/files/00000000-0000-0000-0000-000000000000/")

    assert response.status_code == 404


def test_measurements_are_paginated(client):
    file_id = upload(client, "survey.kml", KML.encode()).json()["id"]

    page = client.get(f"/api/files/{file_id}/measurements/?limit=2&offset=2").json()

    assert page["total"] == 3
    assert [i["feature_index"] for i in page["items"]] == [2]
