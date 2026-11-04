"""Compact agricultural-relevance report matches the result-page ranking."""

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


def test_agricultural_summary_contains_four_counts_and_sorted_regions():
    regions = {
        "少量区域": {"total": 1, "counts": {"较低相关": 1}},
        "最多区域": {"total": 6, "counts": {"可能相关": 5, "较低相关": 1}},
        "其次区域": {"total": 3, "counts": {"较低相关": 3}},
    }
    report = _render({
        "available": True,
        "counts": {"较高相关": 0, "可能相关": 5, "较低相关": 5, "证据不足": 0},
        "total_observations": 10,
        "land_cover_product": "MCD12Q1",
        "land_cover_year": 2024,
        "land_cover_matched": 10,
        "calendar_rules_count": 0,
        "regions": regions,
        "disclaimer": "一整段不适合重复输出的说明文字",
    })
    text = "\n".join(p.text for p in report.paragraphs)
    for phrase in ("较高相关 0", "可能相关 5", "较低相关 5", "证据不足 0",
                   "地表匹配 10 / 10 条", "MCD12Q1 2024", "农事规则 0 条"):
        assert phrase in text
    assert text.index("最多区域 6 条") < text.index("其次区域 3 条")
    assert text.index("其次区域 3 条") < text.index("少量区域 1 条")
    assert "一整段不适合重复输出的说明文字" not in text
    assert text.count("较高相关") == 1


def test_no_agricultural_section_when_there_are_no_valid_observations():
    report = _render({"available": False, "counts": {}, "regions": {}})
    text = "\n".join(p.text for p in report.paragraphs)
    assert "农业秸秆焚烧相关性分析" not in text
