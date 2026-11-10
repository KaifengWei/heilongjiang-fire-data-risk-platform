"""Historical weather, FIRMS observations and real land-cover evidence parity."""

from io import BytesIO
from pathlib import Path

from docx import Document

from fire_monitor.app import create_app
from fire_monitor.services.historical_weather_context_service import (
    HistoricalWeatherContextService,
)
from fire_monitor.services.weather_observation_synthesis_service import (
    build_joint_historical_evidence,
)


def _weather():
    return {
        "available": True, "mode": "historical",
        "source": "NASA POWER Daily",
        "representative_point": {
            "longitude": 124.12, "latitude": 45.62, "cell_count": 2,
        },
        "period": {
            "start": "2026-04-01", "end": "2026-04-02",
            "metrics": {
                "humidity_percent": 55.0, "wind_mps": 5.5,
                "precipitation_mm": 0.8, "temperature_c": 7.0,
            },
        },
        "peak_day": {
            "date": "2026-04-01", "fire_count": 2, "metrics": {
                "humidity_percent": 35.0, "wind_mps": 4.9,
                "precipitation_mm": 0.0, "temperature_c": 2.1,
            }, "summary": "test-only",
        },
        "daily_comparison": [
            {"date": "2026-04-01", "fire_count": 2,
             "humidity_percent": 35, "wind_mps": 4.9,
             "precipitation_mm": 0.0, "temperature_c": 2.1},
            {"date": "2026-04-02", "fire_count": 1,
             "humidity_percent": 75, "wind_mps": 6.1,
             "precipitation_mm": 1.6, "temperature_c": 11.9},
        ],
        "counties": [],
    }


def _decisions():
    return {
        "spatial": {"bbox": [124.0, 45.5, 124.25, 45.75], "count": 2},
        "top_grid_comparison": [
            {"count": 2, "surface_matched": 2,
             "cropland_background_count": 2},
        ],
    }


def test_joint_evidence_uses_true_metrics_and_same_grid_land_cover():
    result = build_joint_historical_evidence(_weather(), _decisions())
    assert result["available"]
    assert result["peak_date"] == "2026-04-01"
    assert result["sample_in_primary_grid"]
    assert len(result["blocks"]) == 3
    day, location, land = [row["text"] for row in result["blocks"]]
    assert "2026-04-01 共记录 2 条" in day
    assert "相对湿度 35 %" in day
    assert "低20个百分点" in day
    assert "日降水量 0.0 mm" in day
    assert "平均气温 2.1 ℃" in day
    assert "东经 124.1200°" in location
    assert "累计观测最多的 0.25° 网格" in location
    assert "2 条匹配" in land
    assert "2 条位于耕地" in land


def test_missing_metrics_and_nonmatching_sample_do_not_fabricate_joint_land_context():
    weather = _weather()
    weather["representative_point"]["longitude"] = 125.0
    weather["daily_comparison"][0]["humidity_percent"] = None
    weather["period"]["metrics"]["humidity_percent"] = None
    result = build_joint_historical_evidence(weather, _decisions())
    assert result["available"]
    assert len(result["blocks"]) == 2
    assert "相对湿度" not in result["blocks"][0]["text"]
    assert "不能直接代表其他火点集中网格" in result["blocks"][1]["text"]
    assert not build_joint_historical_evidence({"available": False})["available"]
    weather["daily_comparison"] = [
        {"date": "2026-04-01", "fire_count": 0, "humidity_percent": None},
    ]
    assert not build_joint_historical_evidence(weather)["available"]


def test_historical_api_and_word_export_share_joint_evidence(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "fire.sqlite",
        uploads_root=tmp_path / "uploads", testing=True,
    )
    cover = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(cover, "_open", lambda: True)
    monkeypatch.setattr(
        cover, "_sample",
        lambda longitude, latitude: 12 if longitude < 125 else None,
    )

    def weather_stub(self, *, task_id, rows, cached_only=False):
        assert len(rows) == 3
        return _weather()

    monkeypatch.setattr(
        HistoricalWeatherContextService, "analyze_coordinate_task",
        weather_stub,
    )

    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "45.62,124.12,2026-04-01,0320,N,VIIRS,n,2.0NRT,8.5\n"
        "45.63,124.13,2026-04-01,0330,N,VIIRS,n,2.0NRT,9.0\n"
        "45.83,125.01,2026-04-02,0335,N,VIIRS,n,2.0NRT,4.2\n"
    )
    client = app.test_client()
    response = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode("utf-8")), "firms.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    task_id = response.headers["Location"].rstrip("/").split("/")[-1]

    api = client.get(f"/api/tasks/{task_id}/weather-context")
    assert api.status_code == 200
    data = api.get_json()
    joint = data["joint_evidence"]
    assert joint["available"]
    assert len(joint["blocks"]) == 3

    report = client.get(f"/tasks/{task_id}/report.docx")
    assert report.status_code == 200
    document = Document(BytesIO(report.data))
    paragraphs = "\n".join(p.text for p in document.paragraphs)
    assert "火点、天气与地表证据对照" in paragraphs
    for row in joint["blocks"]:
        assert row["title"] in paragraphs
        assert row["text"] in paragraphs
    assert "2 条位于耕地" in paragraphs
    assert "火点日期与天气变化对照" in paragraphs

    root = Path(__file__).resolve().parents[1]
    frontend = (root / "static" / "weather_context.js").read_text(encoding="utf-8")
    css = (root / "static" / "product.css").read_text(encoding="utf-8")
    assert "renderJointEvidence(data)" in frontend
    assert "body.textContent = block.text" in frontend
    assert ".weather-joint-evidence" in css
