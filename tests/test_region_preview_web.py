from io import BytesIO
import json
from fire_monitor.app import create_app


def test_region_preview_accepts_user_geojson_without_mutating_database(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    polygon = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "示例市", "level": "city"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [110, 30], [111, 30], [111, 31], [110, 31], [110, 30]
         ]]}}
    ]}
    res = client.post("/api/region-preview", data={
        "files": (BytesIO(b"latitude,longitude,acq_date\n30.5,110.5,2026-01-01\n"), "firms.csv"),
        "boundary_file": (BytesIO(json.dumps(polygon).encode()), "district.geojson")
    }, content_type="multipart/form-data")
    assert res.status_code == 200
    data = res.get_json()
    assert data["matched_rows"] == 1
    assert data["candidates"][0]["name"] == "示例市"
    assert app.extensions["fire_database"].list_regions() == []


def test_region_preview_empty_boundary_does_not_infer_region(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    res = app.test_client().post("/api/region-preview", data={
        "files": (BytesIO(b"latitude,longitude\n30.5,110.5\n"), "firms.csv")
    }, content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["candidates"] == []

def test_region_preview_web_returns_outline_for_map(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    db = app.extensions["fire_database"]
    db.upsert_regions([{"name": "示例市", "level": "city", "geometry": {
        "type": "Polygon", "coordinates": [[[110, 30], [111, 30], [111, 31], [110, 31], [110, 30]]]
    }}])
    response = app.test_client().post("/api/region-preview", data={
        "files": (BytesIO(b"latitude,longitude\\n30.5,110.5\\n"), "firms.csv")
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["candidates"][0]["name"] == "示例市"
    assert payload["sampled_points"] == [[110.5, 30.5]]
    assert payload["preview_shapes"]["features"][0]["geometry"]["type"] == "Polygon"
