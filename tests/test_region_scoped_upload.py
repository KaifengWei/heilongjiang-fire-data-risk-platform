"""Task-scoped boundary regression tests for the configurable-area workflow."""
from io import BytesIO
import json

from fire_monitor.app import create_app


def _polygon(name, x1, y1, x2, y2):
    return {
        "name": name,
        "level": "city",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]
            ]],
        },
    }


def _csv(points):
    header = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,"
        "confidence,version,frp\n"
    )
    return (header + "".join(
        f"{lat},{lon},2026-03-15,0320,N,VIIRS,n,2.0NRT,8.5\n"
        for lat, lon in points
    )).encode("utf-8")


def _post_scoped(client, coordinates, selected_id, polygon=None):
    data = {
        "files": (BytesIO(_csv(coordinates)), "firms.csv"),
        "selected_region_id": str(selected_id),
    }
    if polygon is not None:
        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature",
                 "properties": {"name": polygon["name"], "level": "city"},
                 "geometry": polygon["geometry"]}
            ],
        }
        data["boundary_file"] = (
            BytesIO(json.dumps(feature_collection).encode("utf-8")),
            "boundary.geojson",
        )
    return client.post("/analyze", data=data, content_type="multipart/form-data", follow_redirects=False)


def _task_id(response):
    assert response.status_code == 302, response.get_data(as_text=True)[:1000]
    return response.headers["Location"].rstrip("/").split("/")[-1]


def test_builtin_region_selection_filters_other_regions_and_map(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    db = app.extensions["fire_database"]
    db.upsert_regions([
        _polygon("甲市", 110, 30, 111, 31),
        _polygon("乙市", 112, 32, 113, 33),
    ])

    client = app.test_client()
    task_id = _task_id(_post_scoped(client, [(30.5, 110.5), (32.5, 112.5)], 0))

    task = db.get_analysis_task(task_id)
    assert task["parameters"]["selected_region"]["name"] == "甲市"
    assert [row["name"] for row in db.list_task_regions(task_id)] == ["甲市"]
    stats = app.extensions["statistics_service"].task_region_statistics(task_id)
    assert [(row["region_name"], row["active_fire_count"]) for row in stats] == [("甲市", 1)]

    api = client.get(f"/api/tasks/{task_id}/map-data")
    assert api.status_code == 200
    assert api.get_json()["point_count"] == 1
    boundary = db.task_region_feature_collection(task_id)
    assert [row["properties"]["name"] for row in boundary["features"]] == ["甲市"]


def test_custom_geojson_scope_does_not_modify_builtin_regions(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    task_id = _task_id(_post_scoped(
        client, [(30.5, 110.5)], 0, _polygon("自定义区", 110, 30, 111, 31)
    ))
    db = app.extensions["fire_database"]
    assert db.list_regions() == []
    assert db.list_task_regions(task_id)[0]["name"] == "自定义区"
    rows = app.extensions["statistics_service"].task_firms_observations(task_id)
    assert len(rows) == 1
    assert rows[0]["region_name"] == "自定义区"
    assert "自定义区" in client.get(f"/tasks/{task_id}").get_data(as_text=True)


def test_reusing_observation_keeps_different_task_region_names(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    a_id = _task_id(_post_scoped(client, [(30.5, 110.5)], 0, _polygon("甲区", 110, 30, 111, 31)))
    b_id = _task_id(_post_scoped(client, [(30.5, 110.5)], 0, _polygon("乙区", 110, 30, 111, 31)))
    db = app.extensions["fire_database"]
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM active_fire_observations").fetchone()[0]
    assert count == 1
    service = app.extensions["statistics_service"]
    assert service.task_firms_observations(a_id)[0]["region_name"] == "甲区"
    assert service.task_firms_observations(b_id)[0]["region_name"] == "乙区"
    assert service.task_region_statistics(a_id)[0]["region_name"] == "甲区"
    assert service.task_region_statistics(b_id)[0]["region_name"] == "乙区"


def test_unmatched_candidate_cannot_start_task(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    app.extensions["fire_database"].upsert_regions([_polygon("甲市", 110, 30, 111, 31)])
    response = _post_scoped(app.test_client(), [(40.0, 120.0)], 0)
    assert response.status_code == 400
    assert "没有有效匹配" in response.get_data(as_text=True)
    assert app.extensions["fire_database"].list_analysis_tasks() == []
