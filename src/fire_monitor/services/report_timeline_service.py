"""Compact true-count daily FIRMS timeline for the offline Word report.

No imaging dependency: use an eight-bit RGB PNG encoder from stdlib only.
All bins cover consecutive calendar days, including zero-observation dates.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from io import BytesIO
import math
import re
import struct
import zlib
from typing import Any


_DIGITS = {
    "0": ("111","101","101","101","111"),
    "1": ("010","110","010","010","111"),
    "2": ("111","001","111","100","111"),
    "3": ("111","001","111","001","111"),
    "4": ("101","101","111","001","001"),
    "5": ("111","100","111","001","111"),
    "6": ("111","100","111","101","111"),
    "7": ("111","001","001","001","001"),
    "8": ("111","101","111","101","111"),
    "9": ("111","101","111","001","111"),
    "-": ("000","000","111","000","000"),
}


def _valid_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError, OverflowError):
        return None


def prepare_fire_timeline(
    daily_series: list[dict[str, Any]],
    period: str = "",
    max_bars: int = 42,
) -> dict[str, Any] | None:
    """Keep all days, but group consecutive days when the span is long."""
    if max_bars < 2:
        raise ValueError("max_bars must be at least two")
    counts: Counter[date] = Counter()
    for row in daily_series:
        if not isinstance(row, dict):
            continue
        day = _valid_day(row.get("date"))
        try:
            count = int(row.get("active_fire_observation_count"))
        except (TypeError, ValueError, OverflowError):
            continue
        if day is not None and count >= 0:
            counts[day] += count
    if not counts:
        return None

    start, end = min(counts), max(counts)
    given = re.findall(r"\d{4}-\d{2}-\d{2}", period or "")
    if len(given) >= 2:
        requested_start, requested_end = _valid_day(given[0]), _valid_day(given[1])
        if (
            requested_start is not None and requested_end is not None
            and requested_start <= start <= end <= requested_end
            and (requested_end - requested_start).days <= 3660
        ):
            start, end = requested_start, requested_end

    span = (end - start).days + 1
    group_days = max(1, math.ceil(span / max_bars))
    group_count = math.ceil(span / group_days)
    bins = [{
        "start": start + timedelta(days=i * group_days),
        "end": min(end, start + timedelta(days=(i + 1) * group_days - 1)),
        "count": 0,
    } for i in range(group_count)]
    for day, count in counts.items():
        if start <= day <= end:
            bins[(day - start).days // group_days]["count"] += count

    total = sum(row["count"] for row in bins)
    daily_peak = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0]
    active_days = sum(1 for value in counts.values() if value > 0)
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "span_days": span, "group_days": group_days,
        "active_days": active_days, "total": total,
        "peak_date": daily_peak[0].isoformat(), "peak_count": daily_peak[1],
        "bins": bins,
    }



def prepare_web_fire_timeline(
    daily_series: list[dict[str, Any]],
    period: str = "",
    max_bars: int = 32,
) -> dict[str, Any] | None:
    """Compact, genuine daily bars for the result page.

    Identical date/binning semantics to the Word report, without downloading
    or requesting another data series. A tiny visible positive bar is a UI
    visibility floor, not a modification of the raw count.
    """
    prepared = prepare_fire_timeline(daily_series, period, max_bars=max_bars)
    if not prepared:
        return None
    bins = prepared["bins"]
    max_count = max(1, max(bin_["count"] for bin_ in bins))
    bars = []
    for bin_ in bins:
        count = int(bin_["count"])
        bars.append({
            "start": bin_["start"].isoformat(),
            "end": bin_["end"].isoformat(),
            "count": count,
            "height_percent": (
                round(max(2.5, count * 100 / max_count), 2) if count else 0
            ),
            "is_peak": count == max_count and count > 0,
        })
    return {
        "bars": bars,
        "group_days": prepared["group_days"],
        "span_days": prepared["span_days"],
        "start": prepared["start"],
        "end": prepared["end"],
        "middle": bars[len(bars) // 2]["start"],
        "peak_date": prepared["peak_date"],
        "peak_count": prepared["peak_count"],
        "total": prepared["total"],
    }


def render_fire_timeline_png(timeline: dict[str, Any], width: int = 920, height: int = 310) -> bytes:
    """Rasterized chart with numeric scales and dates; no fonts to bundle."""
    if width < 400 or height < 210:
        raise ValueError("chart dimensions too small")
    bins = timeline.get("bins") or []
    if not bins:
        raise ValueError("timeline has no bins")
    background = (250, 253, 254)
    image = bytearray(bytes(background) * (width * height))
    blue = (94, 158, 184)
    orange = (207, 120, 67)
    ink = (77, 113, 131)
    grid = (215, 232, 239)
    left, right, top, bottom = 63, width - 20, 18, height - 53
    graph_w, graph_h = right - left, bottom - top
    maximum = max(int(row["count"]) for row in bins)
    ceiling = max(1, maximum)

    def pixel(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            idx = (y * width + x) * 3
            image[idx:idx + 3] = bytes(color)

    def rectangle(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, x1 = max(0, x0), min(width, x1)
        y0, y1 = max(0, y0), min(height, y1)
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            off = (y * width + x0) * 3
            image[off:off + len(row)] = row

    def label(value: str, x: int, y: int, scale: int = 2) -> None:
        for char in value:
            bitmap = _DIGITS.get(char)
            if bitmap:
                for row_i, row in enumerate(bitmap):
                    for col_i, bit in enumerate(row):
                        if bit == "1":
                            rectangle(
                                x + col_i * scale, y + row_i * scale,
                                x + (col_i + 1) * scale, y + (row_i + 1) * scale,
                                ink,
                            )
            x += 4 * scale

    for i in range(5):
        y = bottom - round(i * graph_h / 4)
        for x in range(left, right, 7):
            rectangle(x, y, min(x + 4, right), y + 1, grid)
        value = round(ceiling * i / 4)
        text = str(value)
        label(text, left - 11 - len(text) * 8, y - 5)

    pitch = graph_w / len(bins)
    bar_width = max(2, min(21, math.floor(pitch * .72)))
    max_bin = max(int(b["count"]) for b in bins)
    for idx, item in enumerate(bins):
        count = max(0, int(item["count"]))
        if count == 0:
            continue
        mid = left + round((idx + .5) * pitch)
        x = mid - bar_width // 2
        top_of_bar = bottom - max(2, round((count / ceiling) * graph_h))
        rectangle(x, top_of_bar, x + bar_width, bottom, orange if count == max_bin else blue)

    label_step = max(1, math.ceil(len(bins) / 7))
    for idx in range(0, len(bins), label_step):
        day = bins[idx]["start"]
        value = day.strftime("%m-%d") if timeline["span_days"] <= 366 else day.strftime("%y-%m")
        x = left + round((idx + .5) * pitch) - len(value) * 4
        label(value, max(0, min(width - len(value) * 8, x)), bottom + 11)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
        )
    raw = b"".join(
        b"\x00" + image[row * width * 3:(row + 1) * width * 3]
        for row in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
