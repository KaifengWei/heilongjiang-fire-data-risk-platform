from io import BytesIO
from docx import Document
from fire_monitor.app import create_app

CSV = (b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
       b"30.5,110.5,2026-03-15,0320,N,VIIRS,n,2.0NRT,8.5\n"
       b"45.5,127.5,2026-03-16,0320,N,VIIRS,n,2.0NRT,5.0\n")

def make(tmp_path):
    return create_app(database_path=tmp_path / "db.sqlite", uploads_root=tmp_path / "uploads", testing=True)

def upload(client, **args):
    response = client.post("/analyze", data={"files": (BytesIO(CSV), "firms.csv"), **args},
                           content_type="multipart/form-data")
    return response

def tid(r):
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    return r.headers["Location"].rstrip("/").split("/")[-1]

def test_no_polygon_still_analyzes_all_csv_points(tmp_path, monkeypatch):
    # Offline case is deterministic and must not request NASA data.
    from fire_monitor.services.historical_weather_context_service import (
        HistoricalWeatherContextService,
    )
    monkeypatch.setattr(
        HistoricalWeatherContextService, "_fetch_power",
        lambda self, **kwargs: None,
    )
    app = make(tmp_path)
    db = app.extensions["fire_database"]
    assert db.list_regions() == []
    client = app.test_client()
    task = tid(upload(client, area_label="用户关注区域"))
    assert db.list_task_regions(task) == []
    assert db.get_analysis_task(task)["parameters"]["area_mode"] == "coordinates_only"
    rows = app.extensions["statistics_service"].task_firms_observations(task)
    assert len(rows) == 2
    assert {x["region_name"] for x in rows} == {"用户关注区域"}
    html = client.get(f"/tasks/{task}").get_data(as_text=True)
    assert "地表数据尚未覆盖该范围" in html
    assert 'id="mapZoomIn"' in html
    assert 'id="mapZoomOut"' in html
    assert "map_viewport.js?v=release20261105b" in html
    assert "当前情况与建议" in html
    assert "地表核查" in html
    assert "通用农业区域概念示意" not in html
    assert "110.5" in html
    assert client.get(f"/api/tasks/{task}/map-data").get_json()["point_count"] == 2
    assert client.get(f"/api/tasks/{task}/weather-context").get_json()["available"] is False
    report = client.get(f"/tasks/{task}/report.docx")
    assert report.status_code == 200
    doc = Document(BytesIO(report.data))
    report_text = "\n".join(p.text for p in doc.paragraphs)
    assert "空间位置与火点分布" in report_text
    assert "110.50000°E" in report_text
    assert len(doc.inline_shapes) >= 1
    assert "未经行政边界核验" not in report_text

def test_requested_rectangle_filters_and_invalid_rejected(tmp_path):
    app = make(tmp_path)
    client = app.test_client()
    task = tid(upload(client, request_bbox="110,30,111,31"))
    rows = app.extensions["statistics_service"].task_firms_observations(task)
    assert len(rows) == 1
    assert rows[0]["longitude"] == 110.5
    bad = upload(client, request_bbox="111,31,110,30")
    assert bad.status_code == 400

def test_observation_preview_is_not_download_bbox(tmp_path):
    response = make(tmp_path).test_client().post("/api/observation-preview", data={
        "files": (BytesIO(CSV), "firms.csv")
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    assert response.get_json()["observed_bbox"] == [110.5, 30.5, 127.5, 45.5]

def test_same_records_different_task_names(tmp_path):
    app = make(tmp_path)
    client = app.test_client()
    a = tid(upload(client, area_label="甲区"))
    b = tid(upload(client, area_label="乙区"))
    stats = app.extensions["statistics_service"]
    assert {r["region_name"] for r in stats.task_firms_observations(a)} == {"甲区"}
    assert {r["region_name"] for r in stats.task_firms_observations(b)} == {"乙区"}


def test_one_csv_multiple_coordinate_groups_are_shown_and_exported(tmp_path):
    from docx import Document
    app = make(tmp_path)
    task_id = tid(upload(app.test_client(), area_label="跨地区测试范围"))
    page = app.test_client().get(f"/tasks/{task_id}")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "观测位置分组" in text
    assert "经度 110°" in text
    assert "经度 127°" in text
    assert "不是行政区划分" in text
    report = app.test_client().get(f"/tasks/{task_id}/report.docx")
    assert report.status_code == 200
    doc = Document(BytesIO(report.data))
    report_text = "\n".join(p.text for p in doc.paragraphs)
    assert "空间位置与火点分布" in report_text
    assert "观测经度：110.50000°E ～ 127.50000°E" in report_text
    assert "最高观测量网格：" not in report_text
    assert "优先核查位置与建议" in report_text
    assert "表1 优先核查位置和建议" in report_text
    assert "本次重点" in report_text
    assert len(doc.inline_shapes) >= 1


def test_declared_area_hides_unrelated_fixed_landcover_image(tmp_path, monkeypatch):
    """Available raster evidence must not display an unrelated fixed-area map."""
    app = make(tmp_path)
    context = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(context, "analyze", lambda _rows: {
        "available": True,
        "visual_title": "测试地表证据",
        "guidance": "仅展示本次观测点的地表分析信息。",
    })
    monkeypatch.setattr(context, "build_priority_guidance", lambda _data, _regions: None)
    task_id = tid(upload(app.test_client(), area_label="自定义分析区域"))
    html = app.test_client().get(f"/tasks/{task_id}").get_data(as_text=True)
    assert "测试地表证据" in html
    assert "仅展示本次观测点的地表分析信息" in html
    assert "mcd12q1_2024_landcover.png" not in html


def test_declared_summary_shows_measured_land_cover_shares(tmp_path, monkeypatch):
    """Display only matched FIRMS-point land-cover evidence, not a fake area map."""
    app = make(tmp_path)
    service = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(service, "analyze", lambda _rows: {
        "available": True,
        "visual_title": "农田背景与林地背景并存",
        "guidance": "这是本次有效观测位置的土地覆盖分类。",
        "year": 2024,
        "matched_observations": 2,
        "total_observations": 2,
        "counts": {"agriculture": 1, "forest": 1},
    })
    monkeypatch.setattr(service, "build_priority_guidance", lambda _data, _regions: None)
    task_id = tid(upload(app.test_client(), area_label="作物观察区域"))
    text = app.test_client().get(f"/tasks/{task_id}").get_data(as_text=True)
    assert "农田背景与林地背景并存" in text
    assert "农田及交错植被" in text
    assert "林地" in text
    assert text.count("50.0%") >= 2
    assert "不代表整个区域的地表面积比例" in text
    assert "通用农业区域概念示意" not in text


def test_declared_area_renders_only_real_installed_boundary_context(tmp_path):
    import json
    import re

    app = make(tmp_path)
    database = app.extensions["fire_database"]
    database.upsert_regions([
        {
            "name": "本地参照轮廓",
            "level": "city",
            "geometry": {"type": "Polygon", "coordinates": [[
                [110.1, 30.1], [110.9, 30.1], [110.9, 30.9],
                [110.1, 30.9], [110.1, 30.1],
            ]]},
        },
        {
            "name": "远端轮廓",
            "level": "city",
            "geometry": {"type": "Polygon", "coordinates": [[
                [145, 40], [146, 40], [146, 41], [145, 41], [145, 40],
            ]]},
        },
    ])
    task_id = tid(upload(app.test_client(), request_bbox="110,30,111,31"))
    html = app.test_client().get(f"/tasks/{task_id}").get_data(as_text=True)
    assert 'data-coordinate-mode="true"' in html
    assert "1 处地区轮廓" in html
    match = re.search(r'<script id="taskMapFeatures" type="application/json">(.*?)</script>',
                      html, flags=re.S)
    assert match is not None
    features = json.loads(match.group(1))["features"]
    assert len(features) == 1
    assert features[0]["properties"]["name"] == "本地参照轮廓"
    assert features[0]["properties"]["reference_only"] is True
    assert features[0]["geometry"]["type"] == "Polygon"
    assert app.test_client().get(f"/api/tasks/{task_id}/map-data").get_json()["point_count"] == 1


def test_user_installed_boundary_is_visual_reference_only(tmp_path):
    import json
    import re

    app = make(tmp_path)
    database = app.extensions["fire_database"]
    database.install_user_catalog_regions([{
        "name": "已安装示例边界",
        "level": "custom",
        "geometry": {"type": "Polygon", "coordinates": [[
            [110, 30], [111, 30], [111, 31], [110, 31], [110, 30],
        ]]},
    }], data_source="本地测试文件，不用于正式发布", source_sha256="test-source")
    task_id = tid(upload(app.test_client(), area_label="任意用户名称"))
    page = app.test_client().get(f"/tasks/{task_id}").get_data(as_text=True)
    match = re.search(r'<script id="taskMapFeatures" type="application/json">(.*?)</script>',
                      page, flags=re.S)
    assert match
    features = json.loads(match.group(1))["features"]
    assert [feature["properties"]["name"] for feature in features] == ["已安装示例边界"]
    assert features[0]["properties"]["reference_only"] is True
    assert features[0]["properties"]["source"] == "user_catalog"
    points = app.test_client().get(f"/api/tasks/{task_id}/map-data").get_json()
    assert points["point_count"] == 2
    assert database.list_task_regions(task_id) == []


def test_map_viewport_keeps_observation_bounds_when_reference_is_present(tmp_path):
    app = make(tmp_path)
    app.extensions["fire_database"].upsert_regions([{
        "name": "小范围边界",
        "level": "city",
        "geometry": {"type": "Polygon", "coordinates": [[
            [110, 30], [111, 30], [111, 31], [110, 31], [110, 30],
        ]]},
    }])
    task_id = tid(upload(app.test_client()))
    html = app.test_client().get(f"/tasks/{task_id}").get_data(as_text=True)
    assert 'id="mapZoomModeButton"' in html
    assert "查看轮廓全貌" in html
    assert "不代表行政落区核验或全国底图" not in html
    assert "本次区域名称由用户声明，未核验行政边界" not in html
    js = app.test_client().get("/static/product.js").get_data(as_text=True)
    assert "if ((coordinateMode || !provinceBounds) && points.length)" in js
    assert "showFullOutline = !showFullOutline" in js
    assert "showFullOutline ? provinceBounds : coordinateBounds" in js
