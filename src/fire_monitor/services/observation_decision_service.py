"""Task-grounded observation conclusions for the desktop results and report.

Never infer burning cause, administrative jurisdiction or fire probability from
FIRMS points alone. Findings describe the actual task's observation geography,
date concentration and previously computed multi-date 5 km cells.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from math import floor, isfinite
from statistics import median
from typing import Any


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _observed_date(row: dict[str, Any]) -> str | None:
    value = str(row.get("acquired_date") or "")[:10]
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def build_observation_decisions(
    rows: list[dict[str, Any]],
    firms_intelligence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure, deterministic interpretation of the current task's FIRMS rows.

    Grid bounds are a 0.25-degree search window, not an identified land parcel.
    The sample point comes from an actual row, never from a synthetic center.
    """
    grids: dict[tuple[int, int], list[tuple[float, float, str | None]]] = defaultdict(list)
    daily: Counter[str] = Counter()
    total = 0
    for row in rows:
        try:
            lon, lat = float(row["longitude"]), float(row["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        observed = _observed_date(row)
        grids[(floor(lon * 4), floor(lat * 4))].append((lon, lat, observed))
        if observed:
            daily[observed] += 1
        total += 1

    if not total:
        return {"available": False, "reason": "no_valid_coordinates"}

    ranked = sorted(grids.items(), key=lambda item: (-len(item[1]), item[0]))
    (gx, gy), top_points = ranked[0]
    count = len(top_points)
    share = round(100 * count / total, 1)
    second = len(ranked[1][1]) if len(ranked) > 1 else 0
    cell_day_counts = Counter(day for _, _, day in top_points if day)
    top_date, top_day_count = (
        sorted(cell_day_counts.items(), key=lambda item: (-item[1], item[0]))[0]
        if cell_day_counts else (None, 0)
    )
    candidates = (
        [p for p in top_points if p[2] == top_date]
        if top_date else top_points
    )
    center_lon, center_lat = (gx + 0.5) / 4, (gy + 0.5) / 4
    sample = min(
        candidates,
        key=lambda p: (
            (p[0] - center_lon) ** 2 + (p[1] - center_lat) ** 2,
            p[0], p[1], p[2] or "",
        ),
    )
    west, south, east, north = gx / 4, gy / 4, (gx + 1) / 4, (gy + 1) / 4
    bounds_label = (
        f"东经 {west:.2f}°～{east:.2f}°，"
        f"北纬 {south:.2f}°～{north:.2f}°"
    )
    if len(ranked) > 1:
        if count >= second * 1.5:
            spatial_conclusion = (
                f"首位网格记录 {count:,} 条，占本次有效坐标观测的 {share:.1f}%；"
                f"比第二位多 {count - second:,} 条，空间关注点以此处为先。"
            )
        else:
            spatial_conclusion = (
                f"首位网格记录 {count:,} 条，占 {share:.1f}%；"
                f"第二位有 {second:,} 条。两处数量接近，不能只看首位网格。"
            )
    else:
        spatial_conclusion = (
            f"本次 {total:,} 条有效坐标观测全部落在同一 0.25° 网格。"
        )

    spatial = {
        "count": count,
        "share": share,
        "second_count": second,
        "cell_count": len(ranked),
        "active_days": len(cell_day_counts),
        "bbox": [west, south, east, north],
        "bounds_label": bounds_label,
        "peak_date": top_date,
        "peak_count": top_day_count,
        "sample_point": {
            "longitude": round(sample[0], 5),
            "latitude": round(sample[1], 5),
            "date": sample[2],
        },
        "headline": f"首位网格 {count:,} 条，占 {share:.1f}%",
        "conclusion": spatial_conclusion,
        "evidence": (
            f"{bounds_label}；在 {len(cell_day_counts)} 个日期出现观测"
            + (f"；该网格高值日 {top_date} 有 {top_day_count:,} 条。" if top_date else "。")
        ),
    }

    peak_date, peak_count = (
        sorted(daily.items(), key=lambda item: (-item[1], item[0]))[0]
        if daily else (None, 0)
    )
    active_days = len(daily)
    others = [count for day, count in daily.items() if day != peak_date]
    typical_count = float(median(others)) if others else None
    ratio = round(peak_count / typical_count, 1) if typical_count and typical_count > 0 else None
    peak_share = round(peak_count / total * 100, 1) if total else 0
    if peak_date and ratio is not None:
        temporal_conclusion = (
            f"{peak_date} 共记录 {peak_count:,} 条，占有效坐标观测的 {peak_share:.1f}%；"
            f"其余 {len(others)} 个有观测日的单日中位数为 {typical_count:g} 条，"
            f"该日为其 {ratio:.1f} 倍。"
        )
    elif peak_date:
        temporal_conclusion = (
            f"{peak_date} 共记录 {peak_count:,} 条，占有效坐标观测的 {peak_share:.1f}%；"
            "本次没有其他有观测日用于比较日间变化。"
        )
    else:
        temporal_conclusion = "有效坐标观测没有可用于统计日变化的采集日期。"
    temporal = {
        "peak_date": peak_date,
        "peak_count": peak_count,
        "peak_share": peak_share,
        "active_days": active_days,
        "other_median": typical_count,
        "multiple": ratio,
        "headline": (
            f"{peak_date} 有 {peak_count:,} 条，占 {peak_share:.1f}%"
            if peak_date else "无可比日期"
        ),
        "conclusion": temporal_conclusion,
    }

    repeated = (firms_intelligence or {}).get("repeated_cells") or []
    real_repeat = [
        x for x in repeated
        if _positive_int(x.get("active_days")) >= 2
    ]
    if real_repeat:
        best = real_repeat[0]
        days = _positive_int(best.get("active_days"))
        observations = _positive_int(best.get("observation_count"))
        longest = _positive_int(best.get("longest_consecutive_days"))
        grid_km = float(best.get("grid_km") or 5.0)
        repeated_conclusion = (
            f"共识别 {len(real_repeat)} 个约 {grid_km:g} km 的跨日重复观测网格；"
            f"首位网格在 {days} 个日期记录 {observations:,} 条，"
            f"最早 {best.get('first_date') or '—'}、最晚 {best.get('last_date') or '—'}。"
        )
        if longest >= 2:
            repeated_conclusion += f"其中最长连续出现 {longest} 天。"
        persistence = {
            "count": len(real_repeat),
            "headline": f"{len(real_repeat)} 处网格跨日重复观测",
            "conclusion": repeated_conclusion,
            "active_days": days,
            "observations": observations,
            "longest_consecutive_days": longest,
            "grid_km": grid_km,
            "latitude": best.get("center_latitude"),
            "longitude": best.get("center_longitude"),
        }
    else:
        persistence = {
            "count": 0,
            "headline": "没有跨日重复的局部网格",
            "conclusion": (
                "按当前约 5 km 网格和已记录日期统计，未形成跨日重复网格；"
                "本次应以空间集中的点位和日期高值为主要分析对象。"
            ),
            "active_days": 0,
        }

    # Choose the interpretation from measurements, not a generic review template.
    if peak_date and ratio is not None and ratio >= 2:
        lead = (
            f"本次最突出的变化是 {peak_date} 的单日观测高值："
            f"{peak_count:,} 条，为其他有观测日中位数的 {ratio:.1f} 倍。"
        )
    elif len(ranked) > 1 and count < second * 1.5:
        lead = (
            f"火点分布不能由单一网格代表：首位和第二位分别为 "
            f"{count:,} 条、{second:,} 条。"
        )
    else:
        lead = (
            f"观测最集中的 0.25° 网格有 {count:,} 条，"
            f"占全部有效坐标观测的 {share:.1f}%。"
        )
    if real_repeat:
        lead += f"另外有 {len(real_repeat)} 处约 5 km 网格在不同日期重复出现观测。"

    return {
        "available": True,
        "total": total,
        "lead": lead,
        "spatial": spatial,
        "temporal": temporal,
        "persistence": persistence,
        "priority_order": "按空间集中程度、日期高值和跨日重复记录查看",
    }
