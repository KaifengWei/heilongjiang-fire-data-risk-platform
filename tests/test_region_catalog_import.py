"""Regression tests for persistent, non-overlapping user-supplied boundaries."""
from io import BytesIO
import json

from fire_monitor.app import create_app


def _feature(name, west, south, east, north):
    return {
        "type": "Feature",
        "properties": {"name": name, "level": "custom"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [west, south], [east, south], [east, north],
            [west, north], [west, south]
        ]]},
    }


def _upload(client, features, source="测试机构公开数据 2026", authorized="yes"):
    raw = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    return client.post(
        "/api/region-catalog/import",
        data={
            "boundary_file": (BytesIO(raw), "regions.geojson"),
            "data_source": source,
            "authorized": authorized,
        },
        content_type="multipart/form-data",
    )


def test_installed_boundary_persists_across_app_restart_and_matches_csv(tmp_path):
    db_path, uploads = tmp_path / "db.sqlite", tmp_path / "uploads"
    app = create_app(database_path=db_path, uploads_root=uploads, testing=True)
    client = app.test_client()
    res = _upload(client, [_feature("示例甲区", 110, 30, 111, 31)])
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["installed_count"] == 1

    # A newly created app reads installed boundaries from the same database.
    restarted = create_app(database_path=db_path, uploads_root=uploads, testing=True)
    test_client = restarted.test_client()
    report = test_client.get("/api/region-catalog").get_json()
    assert report["builtin_count"] == 0
    assert report["installed_count"] == 1
    assert report["installed"][0]["data_source"] == "测试机构公开数据 2026"
    preview = test_client.post(
        "/api/region-preview",
        data={"files": (BytesIO(b"latitude,longitude\n30.5,110.5\n"), "firms.csv")},
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200, preview.get_json()
    assert preview.get_json()["candidates"][0]["name"] == "示例甲区"


def test_catalog_install_cannot_override_or_overlap_existing_regions(tmp_path):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads", testing=True
    )
    client = app.test_client()
    assert _upload(client, [_feature("甲区", 110, 30, 111, 31)]).status_code == 200
    duplicate = _upload(client, [_feature("甲区", 112, 32, 113, 33)])
    assert duplicate.status_code == 400
    overlap = _upload(client, [_feature("重叠区", 110.5, 30.5, 111.5, 31.5)])
    assert overlap.status_code == 400
    touching = _upload(client, [_feature("相邻区", 111, 30, 112, 31)])
    assert touching.status_code == 200
    stored = app.extensions["fire_database"].list_user_catalog_regions()
    assert {row["name"] for row in stored} == {"甲区", "相邻区"}


def test_catalog_rejects_missing_provenance_and_permission(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    feature = [_feature("甲区", 110, 30, 111, 31)]
    assert _upload(client, feature, source="x").status_code == 400
    assert _upload(client, feature, authorized="no").status_code == 400
    assert app.extensions["fire_database"].list_user_catalog_regions() == []


def test_builtin_catalog_collision_is_rejected_without_overwrite(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)
    db = app.extensions["fire_database"]
    f = _feature("已有市", 110, 30, 111, 31)
    db.upsert_regions([{"name": "已有市", "level": "city", "geometry": f["geometry"]}])
    res = _upload(app.test_client(), [_feature("外部同名市", 110, 30, 111, 31)])
    assert res.status_code == 400
    assert {x["name"] for x in db.list_regions()} == {"已有市"}
    assert db.list_user_catalog_regions() == []
