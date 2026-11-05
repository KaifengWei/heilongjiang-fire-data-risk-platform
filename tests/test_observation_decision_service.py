"""Decision-grade FIRMS conclusions: factual evidence, on-map actions, export parity."""

from io import BytesIO
from pathlib import Path

from docx import Document

from fire_monitor.app import create_app
from fire_monitor.services.observation_decision_service import build_observation_decisions


def _rows():
    return [
        {"longitude": 124.10, "latitude": 45.10, "acquired_date": "2026-04-01"},
        {"longitude": 124.11, "latitude": 45.12, "acquired_date": "2026-04-01"},
        {"longitude": 124.12, "latitude": 45.13, "acquired_date": "2026-04-01"},
        {"longitude": 124.13, "latitude": 45.15, "acquired_date": "2026-04-02"},
        {"longitude": 125.10, "latitude": 45.10, "acquired_date": "2026-04-02"},
        {"longitude": 125.12, "latitude": 45.13, "acquired_date": "2026-04-03"},
    ]


def _repeats():
    return {"repeated_cells": [{
        "grid_km": 5.0, "active_days": 2, "observation_count": 4,
        "longest_consecutive_days": 2,
        "first_date": "2026-04-01", "last_date": "2026-04-02",
        "center_longitude": 124.1, "center_latitude": 45.12,
    }]}


def test_real_counts_compare_spatial_temporal_and_repeated_cells():
    result = build_observation_decisions(_rows(), _repeats())
    assert result["available"]
    assert result["total"] == 6
    spatial = result["spatial"]
    assert spatial["bbox"] == [124.0, 45.0, 124.25, 45.25]
    assert spatial["count"] == 4
    assert spatial["share"] == 66.7
    assert spatial["active_days"] == 2
    assert spatial["second_count"] == 2
    assert "比第二位多 2 条" in spatial["conclusion"]
    assert spatial["sample_point"]["date"] == "2026-04-01"
    assert (
        spatial["sample_point"]["longitude"],
        spatial["sample_point"]["latitude"],
    ) in {(p["longitude"], p["latitude"]) for p in _rows()}
    temporal = result["temporal"]
    assert temporal["peak_date"] == "2026-04-01"
    assert temporal["peak_count"] == 3
    assert temporal["other_median"] == 1.5
    assert temporal["multiple"] == 2.0
    assert temporal["spatial_overlap_count"] == 3
    assert temporal["spatial_overlap_share"] == 100.0
    assert "全部落在累计首位" in temporal["spatial_overlap"]
    assert "2.0 倍" in temporal["conclusion"]
    assert result["persistence"]["count"] == 1
    assert "最长连续出现 2 天" in result["persistence"]["conclusion"]
    assert "真实地表" not in result["lead"]
    assert "优先去核实" not in result["lead"]


def test_scattered_observations_do_not_claim_single_dominant_hotspot():
    rows = [
        {"longitude": 124.10, "latitude": 45.10, "acquired_date": "2026-04-01"},
        {"longitude": 125.10, "latitude": 45.10, "acquired_date": "2026-04-02"},
    ]
    result = build_observation_decisions(rows, {"repeated_cells": []})
    assert result["available"]
    assert "不能只看首位网格" in result["spatial"]["conclusion"]
    assert "两处数量接近" in result["spatial"]["conclusion"]
    assert result["persistence"]["count"] == 0


def test_missing_dates_and_coordinates_are_not_invented():
    assert not build_observation_decisions([
        {"longitude": None, "latitude": 45.0},
        {"longitude": float("nan"), "latitude": 45.0},
    ])["available"]
    result = build_observation_decisions([
        {"longitude": 124.15, "latitude": 45.11},
    ], {"repeated_cells": []})
    assert result["available"]
    assert result["temporal"]["peak_date"] is None
    assert result["spatial"]["sample_point"]["date"] is None
    assert result["spatial"]["active_days"] == 0


def test_decision_panel_uses_real_task_counts_and_matches_word(tmp_path):
    app = create_app(
        database_path=tmp_path / "decision.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    client = app.test_client()
    header = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,"
        "confidence,version,frp\n"
    )
    csv = header + "".join(
        f"{point['latitude']},{point['longitude']},{point['acquired_date']},"
        f"{300 + index},N,VIIRS,n,2.0NRT,{3.0 + index}\n"
        for index, point in enumerate(_rows())
    )
    submitted = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode("utf-8")), "analysis.csv")},
        content_type="multipart/form-data",
    )
    assert submitted.status_code == 302
    page = client.get(submitted.headers["Location"])
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "从本次观测得出的三个结论" in html
    assert "首位网格 4 条，占 66.7%" in html
    assert 'data-map-focus-bbox="124.0,45.0,124.25,45.25"' in html
    assert 'data-map-date="2026-04-01"' in html
    assert "先确认真实地表，再核对热异常来源" not in html
    task_id = submitted.headers["Location"].rstrip("/").split("/")[-1]
    response = client.get(f"/tasks/{task_id}/report.docx")
    assert response.status_code == 200
    doc = Document(BytesIO(response.data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "本次观测形成的主要结论" in text
    assert "首位网格记录 4 条" in text
    assert "个有观测日的单日中位数" in text
    assert "日期与空间集中位置的重合" in text
    assert "实测样本点为东经" in text


def test_map_focus_event_is_not_just_a_reset_button():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "product.js").read_text(encoding="utf-8")
    assert "document.querySelectorAll('[data-map-focus-bbox]')" in js
    assert "manualViewport = {" in js
    assert "showFullOutline = false" in js
    assert "setSelectedDateIndex(null)" in js


def test_peak_location_can_differ_from_cumulative_top_grid():
    rows = [
        {"longitude": 124.10, "latitude": 45.10, "acquired_date": "2026-04-01"},
        {"longitude": 124.12, "latitude": 45.12, "acquired_date": "2026-04-02"},
        {"longitude": 124.13, "latitude": 45.13, "acquired_date": "2026-04-03"},
        {"longitude": 125.10, "latitude": 45.10, "acquired_date": "2026-04-04"},
        {"longitude": 125.11, "latitude": 45.11, "acquired_date": "2026-04-04"},
    ]
    result = build_observation_decisions(rows, {"repeated_cells": []})
    assert result["spatial"]["count"] == 3
    assert result["temporal"]["peak_date"] == "2026-04-04"
    assert result["temporal"]["spatial_overlap_count"] == 0
    assert "累计最多的空间网格与单日高值位置不同" in result["temporal"]["spatial_overlap"]
