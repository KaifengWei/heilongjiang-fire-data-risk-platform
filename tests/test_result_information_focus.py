"""Result page defaults to user-relevant findings while preserving evidence on demand."""
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from fire_monitor.app import create_app
from fire_monitor.services.weather_observation_synthesis_service import (
    build_joint_historical_evidence,
)


def test_result_template_compiles_and_keeps_on_demand_evidence():
    root = Path(__file__).resolve().parents[1]
    Environment(loader=FileSystemLoader(str(root / "templates"))).get_template(
        "task_detail.html"
    )
    template = (root / "templates" / "task_detail.html").read_text(encoding="utf-8")
    assert '<details class="result-data-method result-grid-more">' in template
    assert '<summary>查看其余网格</summary>' in template
    assert '<summary>查看相关性分类明细</summary>' in template
    assert 'class="action-guidance-facts result-decision-readouts"' not in template
    assert 'data-map-focus-bbox="{{ observation_decisions.spatial.bbox|join' in template
    assert 'data-map-date="{{ observation_decisions.temporal.peak_date }}"' in template
    assert 'data-map-theme="persistent"' in template
    assert '<summary>样本来源' not in template  # optional evidence is named plainly
    assert "查看样本来源与统计口径" in template


def test_result_page_avoids_visible_redundant_long_paragraphs(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "result.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    land = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(land, "_open", lambda: True)
    monkeypatch.setattr(land, "_sample",
                        lambda longitude, latitude: 12 if longitude < 120 else None)
    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "30.5,110.5,2026-04-01,0320,N,VIIRS,n,2.0NRT,8.5\n"
        "30.6,110.6,2026-04-01,0325,N,VIIRS,n,2.0NRT,7.5\n"
        "45.5,127.5,2026-04-03,0330,N,VIIRS,n,2.0NRT,6.2\n"
    )
    client = app.test_client()
    sent = client.post("/analyze", data={
        "files": (BytesIO(csv.encode("utf-8")), "firms.csv"),
    }, content_type="multipart/form-data")
    assert sent.status_code == 302
    page = client.get(sent.headers["Location"])
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "共匹配 2 / 3 条观测" in html  # detailed provenance is retained
    assert "查看匹配范围与统计口径" in html
    assert "已匹配 2 条火点" in html
    assert "位置与统计明细" in html
    assert "日期与空间对照明细" in html
    assert "查看完整气象与地表对照" not in html  # loaded from weather JS
    assert "查看相关性分类明细" in html
    assert "result-decision-readouts" not in html
    assert "按 1° 经纬网格分组" in html
    assert "当前情况与建议" in html


def test_weather_digest_uses_actual_deltas_and_preserves_full_evidence():
    weather = {
        "available": True,
        "mode": "historical",
        "peak_day": {"date": "2026-04-01", "fire_count": 511},
        "representative_point": {
            "longitude": 124.1, "latitude": 45.1, "cell_count": 91,
        },
        "period": {"metrics": {
            "humidity_percent": 55, "temperature_c": 7.0,
            "precipitation_mm": 0.8,
        }},
        "daily_comparison": [
            {"date": "2026-04-01", "fire_count": 511,
             "humidity_percent": 35, "temperature_c": 2.1,
             "precipitation_mm": 0.0},
        ],
    }
    decisions = {
        "spatial": {"bbox": [124, 45, 124.25, 45.25], "count": 91},
        "temporal": {"peak_focus": {
            "bbox": [125, 45, 125.25, 45.25], "count": 38,
        }},
        "top_grid_comparison": [{
            "count": 91, "surface_matched": 87,
            "cropland_background_count": 84,
        }],
    }
    digest = build_joint_historical_evidence(weather, decisions)
    assert digest["available"]
    assert len(digest["highlights"]) == 3
    assert "511 条火点" in digest["highlights"][0]["title"]
    assert "比任务期低20个百分点" in digest["highlights"][0]["text"]
    assert "比任务期低4.9℃" in digest["highlights"][0]["text"]
    assert "38 条" in digest["highlights"][1]["text"]
    assert "不同网格" in digest["highlights"][1]["text"]
    assert "84 条为耕地及混合植被背景" in digest["highlights"][2]["text"]
    assert len(digest["blocks"]) == 4
    assert "气象数值来自单一代表点" in digest["note"]


def test_weather_js_prefers_short_highlights_but_full_details_remain():
    root = Path(__file__).resolve().parents[1]
    script = (root / "static" / "weather_context.js").read_text(encoding="utf-8")
    assert "result.highlights" in script
    assert "高值日天气与重点位置" in script
    assert "查看完整气象与地表对照" in script
    assert "result-data-method weather-peak-details" in script
    assert "与当天" not in script or "按任务日期对照实际火点数量和取样点的每日天气" not in script
