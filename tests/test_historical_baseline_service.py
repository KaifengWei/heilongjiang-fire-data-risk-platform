from __future__ import annotations

import json

from fire_monitor.services.historical_baseline_service import (
    HistoricalFirmsBaselineService,
)


def _write_baseline(path):
    daily = {}

    for year, total, harbin, suihua in [
        (2019, 100, 30, 10),
        (2020, 110, 35, 11),
        (2021, 120, 38, 12),
        (2022, 130, 40, 13),
        (2023, 140, 42, 14),
        (2024, 150, 45, 15),
        (2025, 999, 900, 90),
    ]:
        daily[f"{year}-04-01"] = {
            "total": total,
            "regions": {
                "哈尔滨市": harbin,
                "绥化市": suihua,
            },
        }

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product_id": "VIIRS_NOAA20_375M",
                "source": "NASA FIRMS Archive",
                "expected_years": [
                    2019,
                    2020,
                    2021,
                    2022,
                    2023,
                    2024,
                    2025,
                ],
                "daily": daily,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _rows(count, region_name):
    return [
        {
            "acquired_date": "2025-04-01",
            "region_name": region_name,
            "satellite": "N20",
        }
        for _ in range(count)
    ]


def test_historical_baseline_excludes_current_task_year(tmp_path):
    path = tmp_path / "baseline.json"
    _write_baseline(path)

    result = HistoricalFirmsBaselineService(path).compare(
        _rows(160, "哈尔滨市"),
        analysis_start="2025-04-01",
        analysis_end="2025-04-01",
    )

    assert result["available"] is True
    assert result["reference_years"] == [
        2019,
        2020,
        2021,
        2022,
        2023,
        2024,
    ]
    assert 2025 not in result["reference_years"]


def test_historical_baseline_produces_user_facing_guidance(tmp_path):
    path = tmp_path / "baseline.json"
    _write_baseline(path)

    rows = (
        _rows(130, "哈尔滨市")
        + _rows(40, "绥化市")
    )

    result = HistoricalFirmsBaselineService(path).compare(
        rows,
        analysis_start="2025-04-01",
        analysis_end="2025-04-01",
    )

    assert result["province_status"] == "明显高于历史同期"
    assert result["priority_regions"]
    assert "建议先查看" in result["guidance"]


def test_historical_baseline_requires_enough_reference_years(tmp_path):
    path = tmp_path / "baseline.json"

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product_id": "VIIRS_NOAA20_375M",
                "expected_years": [2023, 2024],
                "daily": {},
            }
        ),
        encoding="utf-8",
    )

    result = HistoricalFirmsBaselineService(path).compare(
        _rows(10, "哈尔滨市"),
        analysis_start="2025-04-01",
        analysis_end="2025-04-01",
    )

    assert result["available"] is False
    assert result["reason"] == "insufficient_reference_years"


def test_historical_baseline_rejects_mixed_product_comparison(tmp_path):
    path = tmp_path / "baseline.json"
    _write_baseline(path)

    rows = [
        {
            "acquired_date": "2025-04-01",
            "region_name": "哈尔滨市",
            "satellite": "N21",
        }
    ]

    result = HistoricalFirmsBaselineService(path).compare(
        rows,
        analysis_start="2025-04-01",
        analysis_end="2025-04-01",
    )

    assert result["available"] is False
    assert result["reason"] == "current_product_not_noaa20"
