"""Task-grounded historical weather, observation and land-cover evidence.

All comparisons are descriptive. A single NASA POWER coordinate represents
its sampled location, not a region-wide weather field, and an MCD12Q1 class
sample does not identify the cause of a FIRMS thermal anomaly.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any


METRICS = (
    ("humidity_percent", "相对湿度", "%", "个百分点", 0),
    ("wind_mps", "平均风速", "m/s", "m/s", 1),
    ("precipitation_mm", "日降水量", "mm", "mm", 1),
    ("temperature_c", "平均气温", "℃", "℃", 1),
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _valid_date(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        return None


def _format(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def build_joint_historical_evidence(
    weather: dict[str, Any] | None,
    decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine already-measured evidence without additional external requests.

    The leading task date comes from the daily FIRMS/POWER comparison, and all
    weather values refer to the POWER representative point. Only measured
    land-cover matches in the same 0.25-degree cell are described.
    """
    weather = weather or {}
    if not weather.get("available") or weather.get("mode") != "historical":
        return {"available": False}
    rows = [
        row for row in (weather.get("daily_comparison") or [])
        if isinstance(row, dict) and _valid_date(row.get("date"))
        and _number(row.get("fire_count")) is not None
        and _number(row.get("fire_count")) >= 0
    ]
    if not rows:
        return {"available": False}

    top = sorted(
        rows, key=lambda row: (-int(_number(row["fire_count"]) or 0), str(row["date"]))
    )[0]
    day = _valid_date(top["date"])
    daily_count = int(_number(top["fire_count"]) or 0)
    if not daily_count:
        return {"available": False}
    period = (weather.get("period") or {}).get("metrics") or {}
    comparisons = []
    for key, label, unit, change_unit, digits in METRICS:
        on_day = _number(top.get(key))
        reference = _number(period.get(key))
        if on_day is None:
            continue
        comparison = f"{label} {_format(on_day, digits)} {unit}"
        if reference is not None:
            difference = on_day - reference
            if abs(difference) < 10 ** (-digits) / 2:
                comparison += f"，与任务期平均值 {_format(reference, digits)} {unit}基本相同"
            else:
                verb = "高" if difference > 0 else "低"
                comparison += (
                    f"，比任务期平均值 {_format(reference, digits)} {unit}"
                    f"{verb}{_format(abs(difference), digits)}{change_unit}"
                )
        comparisons.append(comparison)

    blocks: list[dict[str, str]] = [{
        "title": "火点最多日期的实际天气",
        "text": (
            f"{day} 共记录 {daily_count:,} 条火点观测；"
            + ("；".join(comparisons[:4]) + "。" if comparisons else "该日缺少可比的气象指标。")
        ),
    }]

    spatial = (decisions or {}).get("spatial") or {}
    point = weather.get("representative_point") or {}
    lon = _number(point.get("longitude"))
    lat = _number(point.get("latitude"))
    bounds = spatial.get("bbox") or []
    same_cell = (
        len(bounds) == 4 and lon is not None and lat is not None
        and all(_number(x) is not None for x in bounds)
        and float(bounds[0]) <= lon < float(bounds[2])
        and float(bounds[1]) <= lat < float(bounds[3])
    )
    if lon is not None and lat is not None:
        count = max(0, int(_number(point.get("cell_count")) or 0))
        if same_cell:
            location = (
                f"NASA POWER 取样点（东经 {lon:.4f}°、北纬 {lat:.4f}°）"
                f"位于本次累计观测最多的 0.25° 网格，"
                f"该网格记录 {int(spatial.get('count') or count):,} 条火点观测。"
            )
        else:
            location = (
                f"NASA POWER 取样点为东经 {lon:.4f}°、北纬 {lat:.4f}°。"
                "这个点位的天气不能直接代表其他火点集中网格。"
            )
        blocks.append({"title": "气象取样点与重点网格", "text": location})

    grid = ((decisions or {}).get("top_grid_comparison") or [])
    first = grid[0] if grid else {}
    land_match = int(first.get("surface_matched") or 0)
    farmland = int(first.get("cropland_background_count") or 0)
    top_count = int(first.get("count") or 0)
    if same_cell and land_match and top_count:
        other = max(0, land_match - farmland)
        blocks.append({
            "title": "同一网格中的土地覆盖证据",
            "text": (
                f"在上述 {top_count:,} 条火点观测中，有 {land_match:,} 条匹配"
                f"到 MCD12Q1 土地覆盖；其中 {farmland:,} 条位于耕地"
                f"或耕地与自然植被混合背景，{other:,} 条位于其他地表背景，"
                f"{top_count - land_match:,} 条未匹配。"
            ),
        })
    return {
        "available": True,
        "mode": "historical",
        "peak_date": day,
        "peak_count": daily_count,
        "sample_in_primary_grid": same_cell,
        "blocks": blocks,
        "note": "气象数值来自单一代表点；日期对照与地表类别均是观测证据，不直接确定热异常成因。",
    }
