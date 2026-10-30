"""FIRMS -> agricultural evidence -> frozen task -> HTML and DOCX."""
from io import BytesIO
import json

import numpy as np
import pytest

gdal = pytest.importorskip("osgeo.gdal")
osr = pytest.importorskip("osgeo.osr")

from docx import Document
from fire_monitor.app import create_app


def _test_raster(path):
    ds = gdal.GetDriverByName("GTiff").Create(str(path), 3, 1, 1, gdal.GDT_Byte)
    ds.SetGeoTransform((110, 1, 0, 40, 0, -1))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(255)
    ds.GetRasterBand(1).WriteArray(np.array([[12, 14, 1]], dtype=np.uint8))
    ds = None


def _rule(months):
    return {"schema_version": 1, "rules": [{
        "region_name": "示例市",
        "crop": "测试作物",
        "months": months,
        "source": "测试用来源，非真实农业时历",
    }]}


def test_upload_frozen_calendar_used_in_html_and_word(tmp_path):
    raster = tmp_path / "lc.tif"
    _test_raster(raster)
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        land_cover_path=raster,
        testing=True,
    )
    store = app.extensions["crop_calendar_store"]
    store.path = tmp_path / "settings" / "calendar.json"
    client = app.test_client()
    db = app.extensions["fire_database"]
    db.upsert_regions([{
        "name": "示例市", "level": "city",
        "geometry": {"type": "Polygon", "coordinates": [[
            [110, 39], [113, 39], [113, 40], [110, 40], [110, 39]
        ]]},
    }])
    response = client.post("/api/agriculture/calendar", data={
        "calendar_file": (BytesIO(json.dumps(_rule([10])).encode()), "rules.json")
    }, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["installed_count"] == 1

    csv_bytes = (
        b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        b"39.5,110.5,2026-10-12,0320,N,VIIRS,n,2.0NRT,8.5\n"
        b"39.5,111.5,2026-10-13,0320,N,VIIRS,n,2.0NRT,5.1\n"
    )
    response = client.post("/analyze", data={
        "files": (BytesIO(csv_bytes), "firms.csv"),
        "area_label": "示例市",
    }, content_type="multipart/form-data", follow_redirects=False)
    assert response.status_code == 302, response.get_data(as_text=True)[:800]
    task_id = response.headers["Location"].rstrip("/").split("/")[-1]
    task = db.get_analysis_task(task_id)
    assert task["parameters"]["agricultural_calendar_rules"][0]["months"] == [10]

    page = client.get(f"/tasks/{task_id}")
    assert page.status_code == 200, page.get_data(as_text=True)[:1000]
    html = page.get_data(as_text=True)
    assert "农业秸秆焚烧相关性识别" in html
    assert "较高相关" in html
    assert "可能相关" in html

    report_response = client.get(f"/tasks/{task_id}/report.docx")
    assert report_response.status_code == 200
    doc = Document(BytesIO(report_response.data))
    doc_text = "\n".join(p.text for p in doc.paragraphs)
    assert "农业秸秆焚烧区域火点检测与分析平台" in doc_text
    assert "农业秸秆焚烧相关性分析" in doc_text

    # New local calendar must not retroactively change this task's evidence.
    store.import_json(json.dumps(_rule([3])).encode())
    assert db.get_analysis_task(task_id)["parameters"]["agricultural_calendar_rules"][0]["months"] == [10]
    assert "较高相关" in client.get(f"/tasks/{task_id}").get_data(as_text=True)


def test_calendar_api_rejects_unsupported_or_unsourced_rules(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite",
                     uploads_root=tmp_path / "uploads", testing=True)
    app.extensions["crop_calendar_store"].path = tmp_path / "calendar.json"
    client = app.test_client()
    bad = _rule([13])
    res = client.post("/api/agriculture/calendar", data={
        "calendar_file": (BytesIO(json.dumps(bad).encode()), "rules.json")
    }, content_type="multipart/form-data")
    assert res.status_code == 400
    assert app.extensions["crop_calendar_store"].load_rules() == []
