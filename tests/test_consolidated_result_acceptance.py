"""Consolidated coordinate-result acceptance: usable land evidence and Word parity."""

from io import BytesIO

from docx import Document

from fire_monitor.app import create_app
from fire_monitor.services.agricultural_relevance_service import (
    summarize_agricultural_surface,
)


CSV = (
    b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
    b"30.5,110.5,2026-03-15,0320,N,VIIRS,n,2.0NRT,8.5\n"
    b"45.5,127.5,2026-03-16,0320,N,VIIRS,n,2.0NRT,5.0\n"
)


def test_surface_summary_uses_matched_points_as_denominator():
    result = summarize_agricultural_surface({
        "total_observations": 1591,
        "land_cover_matched": 360,
        "land_cover_counts": {
            "cropland": 260, "mosaic": 9,
            "other": 91, "unknown": 1231,
        },
        "calendar_rules_count": 0,
    })
    assert result["total"] == 1591
    assert result["matched"] == 360
    assert result["missing"] == 1231
    assert result["farmland"] == 269
    assert result["other"] == 91
    assert result["matched_percent"] == 22.6
    assert result["farmland_among_matched_percent"] == 74.7
    assert "269 条位于耕地或耕地与自然植被混合背景" in result["headline"]
    assert "1,231 条未匹配" in result["headline"]
    assert "没有已配置的当地农事时段规则" in result["calendar_note"]


def test_no_raster_or_legacy_payload_does_not_invent_categories():
    missing = summarize_agricultural_surface({
        "total_observations": 5,
        "land_cover_matched": 0,
        "land_cover_counts": {"unknown": 5},
        "calendar_rules_count": 0,
    })
    assert missing["farmland"] is None or missing["farmland"] == 0
    assert missing["missing"] == 5
    legacy = summarize_agricultural_surface({
        "total_observations": 5, "land_cover_matched": 2,
        "calendar_rules_count": 0,
    })
    assert legacy["farmland"] is None
    assert "暂无可核验的分类明细" in legacy["headline"]


def test_coordinate_result_is_compact_and_word_uses_same_surface_numbers(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    raster = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(raster, "_open", lambda: True)
    monkeypatch.setattr(
        raster, "_sample",
        lambda longitude, latitude: 12 if longitude < 120 else None,
    )
    client = app.test_client()
    uploaded = client.post(
        "/analyze",
        data={"files": (BytesIO(CSV), "firms.csv"), "area_label": "实际观测区域"},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 302
    task_id = uploaded.headers["Location"].rstrip("/").split("/")[-1]

    html = client.get(f"/tasks/{task_id}").get_data(as_text=True)
    assert "本次态势摘要" not in html
    assert "实际地表匹配统计" in html
    assert "本次 2 条观测中有 1 条获得土地覆盖背景" in html
    assert "其中 1 条位于耕地或耕地与自然植被混合背景" in html
    assert "尚未匹配土地覆盖" in html
    assert "查看四级相关性分类明细" in html
    assert "当前情况与建议" in html
    # A single user-declared area has no meaningful multi-region ranking.
    assert "各地区相关性分布" not in html

    exported = client.get(f"/tasks/{task_id}/report.docx")
    assert exported.status_code == 200
    doc = Document(BytesIO(exported.data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "农业地表背景与覆盖情况" in text
    assert "本次 2 条观测中有 1 条获得土地覆盖背景" in text
    assert "另有 1 条未匹配" in text
    assert "没有已配置的当地农事时段规则" in text
