"""Daily FIRMS Word timeline is complete, correctly binned and standalone PNG."""

from datetime import date, timedelta
from io import BytesIO
import struct

import pytest
from docx import Document

from fire_monitor.services.report_timeline_service import (
    prepare_fire_timeline,
    render_fire_timeline_png,
)
from fire_monitor.services.report_docx_service import build_analysis_report_docx


def _day(day: date, count: int) -> dict:
    return {"date": day.isoformat(), "active_fire_observation_count": count}


def test_month_timeline_keeps_zero_days_and_true_peak():
    start = date(2026, 4, 1)
    data = [
        _day(start, 511),
        _day(start + timedelta(days=1), 408),
        _day(start + timedelta(days=13), 100),
        _day(start + timedelta(days=29), 22),
    ]
    t = prepare_fire_timeline(data, "2026-04-01 至 2026-04-30")
    assert t is not None
    assert t["span_days"] == 30
    assert t["active_days"] == 4
    assert t["group_days"] == 1
    assert len(t["bins"]) == 30
    assert sum(item["count"] for item in t["bins"]) == 1041
    assert t["bins"][2]["count"] == 0
    assert t["bins"][29]["count"] == 22
    assert t["peak_date"] == "2026-04-01"
    assert t["peak_count"] == 511
    assert (t["start"], t["end"]) == ("2026-04-01", "2026-04-30")


def test_long_span_groups_real_calendar_period_in_at_most_42_columns():
    start = date(2025, 10, 1)
    end = date(2026, 4, 30)
    t = prepare_fire_timeline(
        [_day(start, 3), _day(end, 8)],
        f"{start.isoformat()} 至 {end.isoformat()}",
    )
    assert t is not None
    assert 1 < t["group_days"] < 10
    assert len(t["bins"]) <= 42
    assert t["bins"][0]["count"] == 3
    assert t["bins"][-1]["count"] == 8
    assert sum(b["count"] for b in t["bins"]) == 11
    assert all(b["count"] == 0 for b in t["bins"][1:-1])
    assert t["active_days"] == 2


def test_invalid_records_never_add_observations_or_extend_period():
    rows = [
        _day(date(2026, 4, 1), 3),
        {"date": "2026-04-02", "active_fire_observation_count": -200},
        {"date": "2026-04-77", "active_fire_observation_count": 900},
        {"date": "2026-04-03", "active_fire_observation_count": "??"},
    ]
    t = prepare_fire_timeline(rows, "2026-04-01 至 2026-04-10")
    assert t["total"] == 3
    assert t["span_days"] == 10
    assert t["bins"][1]["count"] == 0
    assert t["active_days"] == 1
    assert prepare_fire_timeline([rows[1], rows[2], rows[3]]) is None
    with pytest.raises(ValueError):
        prepare_fire_timeline(rows, max_bars=1)


def test_word_timeline_png_is_valid_and_word_has_nonduplicated_chart():
    t = prepare_fire_timeline([
        _day(date(2026, 4, 1), 4),
        _day(date(2026, 4, 2), 7),
        _day(date(2026, 4, 30), 1),
    ], "2026-04-01 至 2026-04-30")
    picture = render_fire_timeline_png(t)
    assert picture[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", picture[16:24])
    assert (width, height) == (920, 310)
    assert len(picture) > 1500

    docx_bytes = build_analysis_report_docx(
        task={"name": "四月观测", "parameters": {"area_mode": "coordinates_only"}},
        analysis_summary={
            "period": "2026-04-01 至 2026-04-30",
            "area_mode": "coordinates_only",
            "active_fire_count": 12,
            "affected_regions": 1,
            "main_region": "本次上传数据范围",
        },
        firms_intelligence={
            "summary": {
                "peak_date": "2026-04-02",
                "peak_count": 7, "active_days": 3, "span_days": 30,
            },
            "regions": [], "repeated_cells": [], "anomaly_days": [],
        },
        historical_baseline={"available": False},
        land_cover_context={"available": False},
        priority_land_cover=None,
        weather_context={"available": False},
        daily_series=[
            _day(date(2026, 4, 1), 4),
            _day(date(2026, 4, 2), 7),
            _day(date(2026, 4, 30), 1),
        ],
    )
    word = Document(BytesIO(docx_bytes))
    body = "\n".join(p.text for p in word.paragraphs)
    assert "任务期火点观测走势" in body
    assert "图1 任务期火点观测数量变化" in body
    assert "2026-04-01 至 2026-04-30" in body
    assert "有火点观测的日期：" in body
    assert "3 / 30 天" in body
    assert "火点高值日期对比" not in body
    assert len(word.inline_shapes) == 1
    assert word.inline_shapes[0].width > 0


def test_short_task_keeps_compact_top_date_bar_table():
    t = prepare_fire_timeline([
        _day(date(2026, 4, 3), 1),
        _day(date(2026, 4, 4), 2),
    ])
    assert t["span_days"] == 2
    assert t["group_days"] == 1
