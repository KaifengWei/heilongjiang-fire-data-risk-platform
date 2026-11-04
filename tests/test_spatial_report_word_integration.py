"""Spatial Word exports must use actual task points and installed GeoJSON."""

from io import BytesIO
import json
import struct

from docx import Document
from fire_monitor.app import create_app


def _upload(client, points, **form):
    rows = [
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp",
    ]
    for index, (lon, lat) in enumerate(points):
        rows.append(f"{lat},{lon},2026-04-{index + 3:02d},0320,N,VIIRS,n,2.0NRT,8.5")
    data = {"files": (BytesIO(("\n".join(rows) + "\n").encode()), "firms.csv")}
    data.update(form)
    return client.post("/analyze", data=data, content_type="multipart/form-data")


def test_report_contains_real_geojson_matched_province_and_png(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite",
                     uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    geojson = {
        "type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {"shapeName": "Jilin Province"},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [123, 44], [126, 44], [126, 46], [123, 46], [123, 44],
             ]]}},
        ],
    }
    install = client.post("/api/map/background", data={
        "background_file": (BytesIO(json.dumps(geojson).encode()), "map.geojson"),
        "source": "geoBoundaries CHN ADM1 test",
        "authorized": "yes",
    }, content_type="multipart/form-data")
    assert install.status_code == 200
    result = _upload(client, [(124.12, 45.12), (124.18, 45.18), (127, 45)])
    assert result.status_code == 302
    task_id = result.location.rsplit("/", 1)[-1]
    response = client.get(f"/tasks/{task_id}/report.docx")
    assert response.status_code == 200
    document = Document(BytesIO(response.data))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "空间位置与火点分布" in text
    assert "吉林 2 条（66.7%）" in text
    assert "匹配点位 2 / 3 条" in text
    assert "124.12000°E" in text
    assert "127.00000°E" in text
    assert "最密集 0.25° 网格" in text
    assert "geoBoundaries CHN ADM1 test" in text
    assert len(document.inline_shapes) >= 1
    assert "本次仅按用户声明范围" not in text
    assert "用户声明的区域名称，未经行政边界核验" not in text


def test_report_works_without_installed_geojson_and_preserves_history(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite",
                     uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    result = _upload(client, [(124.5, 45), (124.7, 45.1)])
    assert result.status_code == 302
    task_id = result.location.rsplit("/", 1)[-1]
    report = client.get(f"/tasks/{task_id}/report.docx")
    assert report.status_code == 200
    document = Document(BytesIO(report.data))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "空间位置与火点分布" in text
    assert "依据 FIRMS 观测经纬度绘制" in text
    assert len(document.inline_shapes) >= 1
