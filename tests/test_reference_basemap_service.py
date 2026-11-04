"""Offline basemap imports are validated and only affect map display."""

from io import BytesIO
import json
import re

from fire_monitor.app import create_app
from fire_monitor.services.reference_basemap_service import ReferenceBasemapStore


def _basemap():
    return json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "已核查参考区"},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [110, 30], [112, 30], [112, 32], [110, 32], [110, 30]
             ]]}},
            {"type": "Feature", "properties": {"name": "不相交区"},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [140, 45], [141, 45], [141, 46], [140, 46], [140, 45]
             ]]}}
        ],
    }, ensure_ascii=False).encode()


def _upload(client, raw=None, **kwargs):
    return client.post("/api/map/background", data={
        "background_file": (BytesIO(raw if raw is not None else _basemap()), "map.geojson"),
        "source": kwargs.get("source", "有来源的测试地图"),
        "authorized": kwargs.get("authorized", "yes"),
    }, content_type="multipart/form-data")


def test_install_reference_basemap_atomic_and_spatially_scoped(tmp_path):
    store = ReferenceBasemapStore(tmp_path)
    assert store.summary()["installed"] is False
    result = store.install(_basemap(), source="测试来源", authorized=True)
    assert result["installed"] is True
    assert result["feature_count"] == 2
    assert len(result["sha256"]) == 64
    assert ReferenceBasemapStore(tmp_path).summary()["source"] == "测试来源"
    features = store.context([110, 30, 112, 32])["features"]
    assert len(features) == 1
    assert features[0]["properties"]["name"] == "已核查参考区"
    assert features[0]["properties"]["reference_only"] is True
    assert features[0]["properties"]["reference_layer"] == "basemap"
    assert store.context([70, 0, 71, 1])["features"] == []


def test_reference_basemap_rejects_unsourced_nonpolygon_and_bad_crs(tmp_path):
    store = ReferenceBasemapStore(tmp_path)
    for raw, source, authorized in [
        (_basemap(), "", True),
        (_basemap(), "示例", False),
        (b'{"type":"Point","coordinates":[110,30]}', "示例", True),
        (b'{"type":"FeatureCollection","crs":{"name":"EPSG:3857"},"features":[]}',
         "示例", True),
    ]:
        try:
            store.install(raw, source=source, authorized=authorized)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid map was accepted.")
    assert not store.path.exists()


def test_imported_basemap_is_display_only_for_declared_csv_task(tmp_path):
    app = create_app(
        database_path=tmp_path / "map.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    client = app.test_client()
    assert client.get("/api/map/background").get_json()["installed"] is False
    response = _upload(client)
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert response.get_json()["feature_count"] == 2

    csv = (
        b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        b"30.5,110.5,2026-03-15,0320,N,VIIRS,n,2.0NRT,8.5\n"
        b"45.5,127.5,2026-03-16,0320,N,VIIRS,n,2.0NRT,5.0\n"
    )
    task = client.post("/analyze", data={"files": (BytesIO(csv), "firms.csv")},
                       content_type="multipart/form-data")
    assert task.status_code == 302
    page = client.get(task.headers["Location"]).get_data(as_text=True)
    assert 'id="mapBackgroundForm"' in page
    assert "地图：有来源的测试地图" in page
    match = re.search(
        r'<script id="taskMapFeatures" type="application/json">(.*?)</script>',
        page, flags=re.S,
    )
    assert match
    features = json.loads(match.group(1))["features"]
    # All installed provinces are embedded for the complete-map toggle,
    # even when some do not intersect this task's observed FIRMS extent.
    assert len(features) == 2
    assert {x["properties"]["name"] for x in features} == {
        "已核查参考区", "不相交区",
    }
    assert all(x["properties"]["reference_layer"] == "basemap" for x in features)
    assert "查看底图全貌" in page
    task_id = task.headers["Location"].rstrip("/").split("/")[-1]
    assert client.get(f"/api/tasks/{task_id}/map-data").get_json()["point_count"] == 2
    assert app.extensions["fire_database"].list_task_regions(task_id) == []


def test_basemap_upload_endpoint_rejects_missing_consent_and_invalid_file(tmp_path):
    app = create_app(
        database_path=tmp_path / "map.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    client = app.test_client()
    assert _upload(client, authorized="no").status_code == 400
    assert _upload(client, raw=b"not a json").status_code == 400
    assert client.get("/api/map/background").get_json()["installed"] is False


def test_installed_background_survives_separate_app_instance(tmp_path):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    first = app.test_client()
    assert _upload(first).status_code == 200
    restarted = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    assert restarted.test_client().get("/api/map/background").get_json()["installed"]



def test_geoboundaries_shape_name_and_full_extent_without_fake_labels(tmp_path):
    """The original province names are preserved and map-wide zoom is real."""
    store = ReferenceBasemapStore(tmp_path)
    raw = json.dumps({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": "Liaoning", "shapeISO": "CN-21"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [120, 40], [123, 40], [123, 42], [120, 42], [120, 40]
                ]]},
            },
            {
                "type": "Feature",
                "properties": {"shapeName": "Guangdong", "shapeISO": "CN-44"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [111, 21], [115, 21], [115, 24], [111, 24], [111, 21]
                ]]},
            },
        ],
    }).encode("utf-8")
    store.install(raw, source="geoBoundaries CHN ADM1", authorized=True)
    assert [x["properties"]["name"] for x in store.full_context()["features"]] == [
        "Liaoning", "Guangdong"
    ]
    assert [x["properties"]["name"] for x in store.context([120, 40, 123, 42])["features"]] == ["Liaoning"]
    assert all(
        len(x["properties"]["label_point"]) == 2
        for x in store.full_context()["features"]
    )


def test_reimport_same_file_recovers_real_names_from_legacy_placeholders(tmp_path):
    """Previously imported GeoJSON remains recoverable without redownload."""
    store = ReferenceBasemapStore(tmp_path)
    raw_old = json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [[
                [100, 30], [101, 30], [101, 31], [100, 31], [100, 30]
            ]]},
        }],
    }).encode("utf-8")
    store.install(raw_old, source="测试旧版", authorized=True)
    assert store.full_context()["features"][0]["properties"]["name"] == ""

    raw_new = json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {"shapeName": "Yunnan"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [100, 30], [101, 30], [101, 31], [100, 31], [100, 30]
            ]]},
        }],
    }).encode("utf-8")
    store.install(raw_new, source="geoBoundaries CHN ADM1", authorized=True)
    assert store.full_context()["features"][0]["properties"]["name"] == "Yunnan"


def test_map_label_collision_logic_is_present_in_runtime_script(tmp_path):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    js = app.test_client().get("/static/product.js").get_data(as_text=True)
    assert "const occupied = []" in js
    assert "occupied.some(" in js
    assert "label_point" in js
    assert "查看底图全貌" in js
    assert "地图区域" in js
