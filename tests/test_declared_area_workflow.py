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

def test_no_polygon_still_analyzes_all_csv_points(tmp_path):
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
    assert "通用农业区域概念示意" in html
    assert "全部观测 · 综合总览" in html
    assert "按卫星来源" in html
    assert "不代表行政区空间归属" in html
    assert "全部地区 · 综合总览" not in html
    assert "110.5" in html
    assert client.get(f"/api/tasks/{task}/map-data").get_json()["point_count"] == 2
    assert client.get(f"/api/tasks/{task}/weather-context").get_json()["available"] is False
    report = client.get(f"/tasks/{task}/report.docx")
    assert report.status_code == 200
    doc = Document(BytesIO(report.data))
    assert "未经行政边界核验" in "\n".join(p.text for p in doc.paragraphs)

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
