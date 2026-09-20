from __future__ import annotations

import pandas as pd
import pytest

from fire_monitor.services.firms_intelligence_service import (
    FirmsIntelligenceService,
)


def _frame() -> pd.DataFrame:
    rows = []

    daily_counts = {
        "2026-08-01": 2,
        "2026-08-02": 2,
        "2026-08-03": 2,
        "2026-08-04": 2,
        "2026-08-05": 20,
    }

    for day, count in daily_counts.items():
        for index in range(count):
            rows.append(
                {
                    "latitude": 45.00 + (index % 2) * 0.002,
                    "longitude": 126.00 + (index % 2) * 0.002,
                    "acq_date": day,
                    "acq_time": "0415",
                    "confidence": "n" if index % 3 else "h",
                    "frp": 10 + index,
                    "daynight": "D" if index % 4 else "N",
                    "region_name": "哈尔滨市",
                }
            )

    rows.extend(
        [
            {
                "latitude": 47.35,
                "longitude": 123.95,
                "acq_date": "2026-08-01",
                "acq_time": "0310",
                "confidence": "n",
                "frp": 8.0,
                "daynight": "N",
                "region_name": "齐齐哈尔市",
            },
            {
                "latitude": 47.35,
                "longitude": 123.95,
                "acq_date": "2026-08-03",
                "acq_time": "0315",
                "confidence": "h",
                "frp": 12.0,
                "daynight": "N",
                "region_name": "齐齐哈尔市",
            },
        ]
    )

    return pd.DataFrame(rows)


def test_intelligence_summary_and_peak():
    result = FirmsIntelligenceService().analyze(_frame())

    assert result.summary["observation_count"] == 30
    assert result.summary["date_start"] == "2026-08-01"
    assert result.summary["date_end"] == "2026-08-05"
    assert result.summary["active_days"] == 5
    assert result.summary["peak_date"] == "2026-08-05"
    assert result.summary["peak_count"] == 20


def test_intelligence_detects_robust_high_day():
    result = FirmsIntelligenceService().analyze(_frame())

    assert result.anomaly_days
    assert result.anomaly_days[0]["date"] == "2026-08-05"
    assert result.anomaly_days[0]["count"] == 20


def test_intelligence_computes_region_density_when_area_is_supplied():
    result = FirmsIntelligenceService().analyze(
        _frame(),
        region_areas_km2={
            "哈尔滨市": 10000.0,
            "齐齐哈尔市": 5000.0,
        },
    )

    harbin = result.regions[0]

    assert harbin["region_name"] == "哈尔滨市"
    assert harbin["observation_count"] == 28
    assert harbin["density_per_1000_km2"] == pytest.approx(2.8)


def test_intelligence_reports_frp_and_daynight():
    result = FirmsIntelligenceService().analyze(_frame())

    assert result.frp["available_count"] == 30
    assert result.frp["max_mw"] > result.frp["median_mw"]

    assert result.daynight["known_count"] == 30
    assert (
        result.daynight["day_count"]
        + result.daynight["night_count"]
        == 30
    )


def test_intelligence_finds_repeated_grid_cells():
    result = FirmsIntelligenceService(grid_km=5.0).analyze(_frame())

    assert result.repeated_cells
    top = result.repeated_cells[0]

    assert top["active_days"] >= 2
    assert top["observation_count"] >= 2
    assert top["grid_km"] == 5.0


def test_intelligence_generates_plain_language_conclusions():
    result = FirmsIntelligenceService().analyze(_frame())

    text = "\n".join(result.conclusions)

    assert "30 条" in text
    assert "哈尔滨市" in text
    assert "2026-08-05" in text


def test_intelligence_requires_core_firms_columns():
    frame = pd.DataFrame(
        {
            "latitude": [45.0],
            "acq_date": ["2026-08-01"],
        }
    )

    with pytest.raises(ValueError):
        FirmsIntelligenceService().analyze(frame)


def test_empty_frame_returns_safe_empty_result():
    result = FirmsIntelligenceService().analyze(
        pd.DataFrame(
            columns=[
                "latitude",
                "longitude",
                "acq_date",
            ]
        )
    )

    assert result.summary["observation_count"] == 0
    assert result.regions == []
    assert result.repeated_cells == []
    assert result.conclusions

def test_intelligence_accepts_database_task_rows():
    rows = [
        {
            "acquired_date": "2026-08-01",
            "acquired_time": "0310",
            "latitude": 45.0,
            "longitude": 126.0,
            "region_name": "哈尔滨市",
            "confidence": "n",
            "frp": 12.0,
            "instrument": "VIIRS",
            "satellite": "NOAA-20",
        },
        {
            "acquired_date": "2026-08-02",
            "acquired_time": "0315",
            "latitude": 45.001,
            "longitude": 126.001,
            "region_name": "哈尔滨市",
            "confidence": "h",
            "frp": 18.0,
            "instrument": "VIIRS",
            "satellite": "NOAA-20",
        },
    ]

    result = FirmsIntelligenceService().analyze(rows)

    assert result.summary["observation_count"] == 2
    assert result.summary["date_start"] == "2026-08-01"
    assert result.summary["date_end"] == "2026-08-02"
    assert result.regions[0]["region_name"] == "哈尔滨市"
    assert result.repeated_cells

def test_repeated_grid_cells_keep_exact_active_dates():
    frame = pd.DataFrame(
        [
            {
                "latitude": 45.0,
                "longitude": 126.0,
                "acq_date": "2026-08-01",
                "frp": 10.0,
                "region_name": "哈尔滨市",
            },
            {
                "latitude": 45.001,
                "longitude": 126.001,
                "acq_date": "2026-08-03",
                "frp": 12.0,
                "region_name": "哈尔滨市",
            },
        ]
    )

    result = FirmsIntelligenceService(
        grid_km=5.0
    ).analyze(frame)

    assert result.repeated_cells

    cell = result.repeated_cells[0]

    assert cell["active_dates"] == [
        "2026-08-01",
        "2026-08-03",
    ]
    assert "2026-08-02" not in cell["active_dates"]
