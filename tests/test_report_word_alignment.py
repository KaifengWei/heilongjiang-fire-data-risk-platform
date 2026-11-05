"""Word stays useful while raw evidence classifications remain on the result page."""

from io import BytesIO

from docx import Document

from fire_monitor.services.report_docx_service import build_analysis_report_docx


def _render(agriculture):
    binary = build_analysis_report_docx(
        task={"name": "测试分析记录", "parameters": {"area_mode": "coordinates_only"}},
        analysis_summary={
            "period": "2026-10-01 至 2026-10-31",
            "active_fire_count": 10,
            "affected_regions": 1,
            "main_region": "测试区域",
            "area_mode": "coordinates_only",
        },
        firms_intelligence={
            "summary": {"active_days": 2, "span_days": 31, "peak_date": "2026-10-12",
                        "peak_count": 6},
            "regions": [],
            "repeated_cells": [],
            "anomaly_days": [],
        },
        historical_baseline={"available": False},
        land_cover_context={"available": False},
        priority_land_cover=None,
        weather_context={"available": False},
        daily_series=[],
        agricultural_relevance=agriculture,
    )
    return Document(BytesIO(binary))


def test_export_replaces_vague_categories_with_a_next_step():
    regions = {
        "少量区域": {"total": 1, "counts": {"较低相关": 1}},
        "最多区域": {"total": 6, "counts": {"可能相关": 5, "较低相关": 1}},
    }
    report = _render({
        "available": True,
        "counts": {"较高相关": 0, "可能相关": 5,
                   "较低相关": 5, "证据不足": 0},
        "total_observations": 10,
        "land_cover_product": "MCD12Q1",
        "land_cover_year": 2024,
        "land_cover_matched": 10,
        "calendar_rules_count": 0,
        "regions": regions,
        "disclaimer": "一整段不适合重复输出的说明文字",
    })
    text = "\n".join(p.text for p in report.paragraphs)
    assert "农业地表核查建议" in text
    assert "核查时将火点坐标与耕地分布" in text
    assert "同期影像及农事作业记录" in text
    for label in ("较高相关 0", "可能相关 5", "较低相关 5", "证据不足 0",
                  "农事规则 0 条", "地表匹配 10 / 10 条"):
        assert label not in text
    assert "一整段不适合重复输出的说明文字" not in text


def test_no_agricultural_section_when_there_are_no_valid_observations():
    report = _render({"available": False, "counts": {}, "regions": {}})
    text = "\n".join(p.text for p in report.paragraphs)
    assert "农业地表核查建议" not in text



def test_hotspot_actions_depend_on_recorded_days_and_real_surface_evidence():
    from fire_monitor.services.report_docx_service import _hotspot_next_action

    crop_multiday = _hotspot_next_action({
        "peak_date": "2026-04-03", "active_days": 3,
        "cropland_background_count": 2, "known_surface_count": 2,
    })
    other_single_day = _hotspot_next_action({
        "peak_date": "2026-04-05", "active_days": 1,
        "cropland_background_count": 0, "known_surface_count": 4,
    })
    unknown_date = _hotspot_next_action({
        "peak_date": None, "active_days": 0,
        "cropland_background_count": 0, "known_surface_count": 0,
    })
    assert "其余 2 个有记录日期" in crop_multiday
    assert "当期收获和秸秆处理记录" in crop_multiday
    assert "先核对 2026-04-05 对应时段" in other_single_day
    assert "非农热源或其他热异常成因" in other_single_day
    assert "本次 FIRMS 观测时间" in unknown_date
    assert "先确定地表类型" in unknown_date
    assert len({crop_multiday, other_single_day, unknown_date}) == 3
    for statement in (crop_multiday, other_single_day, unknown_date):
        assert "可能相关" not in statement
        assert "证据不足" not in statement
