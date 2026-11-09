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
    assert "优先核查位置与建议" in text
    assert "最高观测量网格：" not in text
    assert "表1 优先核查位置和建议" in text
    spatial_cells = "\n".join(
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    )
    assert "东经 124.00°～124.25°" in spatial_cells
    assert "北纬 45.00°～45.25°" in spatial_cells
    assert "高值日 2026-04-03（1 条）" in spatial_cells
    assert "具体核查事项" in spatial_cells
    assert "地图序号及核查范围" in spatial_cells
    assert "位置 1" in spatial_cells
    assert "位置 2" in spatial_cells
    assert "实测点 124.12000°E，45.12000°N" in spatial_cells
    assert "对照 2026-04-03 的卫星影像" in spatial_cells
    assert "再复核其余 1 个有记录日期的点位分布" in spatial_cells
    assert "先核对 2026-04-05 对应时段的卫星影像" in spatial_cells
    assert "以实测点坐标定位高分辨率影像" in spatial_cells
    assert "农业线索" not in spatial_cells
    assert "证据不足" not in spatial_cells
    assert "本次观测形成的主要结论" in text
    assert "本次重点" not in text
    assert "农业地表核查建议" not in text
    assert "图1 本次火点空间分布" in text
    assert "地图数字 1～5 对应下方统计网格中心" in text
    assert "图2 火点高值日期对比" in text
    assert "任务期分段观测变化" in text
    assert "火点热辐射功率与高值观测" in text
    assert "中位数" in text
    assert "第 90 百分位" in text
    assert "2026-04-03 至 2026-04-05" in "\n".join(
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    )
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



def test_month_long_firms_word_has_substantive_task_specific_evidence(tmp_path):
    """A 30-day CSV cannot silently collapse to a sparse summary report.

    This creates reproducible synthetic observations; no external data or
    made-up land-cover/risk claims are used.
    """
    app = create_app(
        database_path=tmp_path / "month.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    client = app.test_client()
    lines = [
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp",
    ]
    for i in range(1591):
        day = i % 30 + 1
        lon = 123.75 + i * .00072
        lat = 44.45 + (i % 120) * .011
        frp = 3.2 + (i % 43) * .37
        lines.append(
            f"{lat:.5f},{lon:.5f},2026-04-{day:02d},0320,N,VIIRS,n,2.0NRT,{frp:.2f}"
        )
    response = client.post(
        "/analyze",
        data={"files": (BytesIO(("\n".join(lines) + "\n").encode()), "month.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    task_id = response.headers["Location"].rstrip("/").split("/")[-1]
    word = client.get(f"/tasks/{task_id}/report.docx")
    assert word.status_code == 200
    document = Document(BytesIO(word.data))
    body = "\n".join(paragraph.text for paragraph in document.paragraphs)
    tables = "\n".join(
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    )
    combined = body + "\n" + tables
    assert "1,591 条有效主动火点观测" in body
    assert "2026-04-01" in body and "2026-04-30" in body
    assert "优先核查位置与建议" in body
    assert "任务期分段观测变化" in body
    assert "火点热辐射功率与高值观测" in body
    assert "第 90 百分位" in body
    assert "实际" not in body or "实测点" in tables
    assert "观测依据" in tables
    assert "观测数" in tables
    assert "具体核查事项" in tables
    assert len(document.inline_shapes) >= 1
    # The older report was only a few hundred characters. This gate
    # measures actual structured evidence, not generated filler text.
    assert len(combined.strip()) >= 1200, len(combined.strip())
