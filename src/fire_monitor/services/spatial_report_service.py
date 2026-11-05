"""Task-scoped spatial evidence for DOCX reports.

Uses the same stored WGS84 GeoJSON as the desktop map and the exact FIRMS
observations associated with the task. Backgrounds are reference data only;
nothing here changes task records, risk assessment or area filtering.
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

from shapely.geometry import Point, shape
from shapely.strtree import STRtree


_PROVINCES = {
    "anhui": "安徽", "beijing": "北京", "chongqing": "重庆",
    "fujian": "福建", "gansu": "甘肃", "guangdong": "广东",
    "guangxi": "广西", "guizhou": "贵州", "hainan": "海南",
    "hebei": "河北", "heilongjiang": "黑龙江", "henan": "河南",
    "hubei": "湖北", "hunan": "湖南", "inner mongolia": "内蒙古",
    "nei mongol": "内蒙古", "jiangsu": "江苏", "jiangxi": "江西",
    "jilin": "吉林", "liaoning": "辽宁", "ningxia": "宁夏",
    "qinghai": "青海", "shaanxi": "陕西", "shandong": "山东",
    "shanghai": "上海", "shanxi": "山西", "sichuan": "四川",
    "tianjin": "天津", "tibet": "西藏", "xizang": "西藏",
    "xinjiang": "新疆", "yunnan": "云南", "zhejiang": "浙江",
    "hong kong": "香港", "macao": "澳门", "macau": "澳门",
    "taiwan": "台湾",
}


def display_place(name: str) -> str:
    """Preserve unknown source labels; only translate recognized names."""
    text = str(name or "").strip()
    key = text.casefold()
    key = re.sub(r"\s+(province|municipality|special administrative region|autonomous region)$", "", key)
    key = re.sub(r"\s+(uyghur|uygur|uighur|hui|zhuang)$", "", key)
    return _PROVINCES.get(key.strip(), text)


def _valid_points(rows: list[dict[str, Any]]) -> list[tuple[float, float]]:
    result = []
    for item in rows:
        try:
            lon, lat = float(item["longitude"]), float(item["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90:
            result.append((lon, lat))
    return result


def summarize_observation_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe temporal concentration and radiative values actually recorded.

    This is not an affected-area calculation or an independent fire count.
    Missing dates and FRP are not filled with fabricated values.
    """
    daily: Counter[date] = Counter()
    frp_rows = []
    for row in rows:
        raw = str(row.get("acquired_date") or "")[:10]
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            day = None
        if day:
            daily[day] += 1
        try:
            frp = float(row.get("frp"))
            lon = float(row.get("longitude"))
            lat = float(row.get("latitude"))
        except (TypeError, ValueError, KeyError):
            continue
        if all(map(math.isfinite, (frp, lon, lat))) and frp >= 0:
            frp_rows.append({"frp": frp, "longitude": lon, "latitude": lat,
                             "date": day.isoformat() if day else None})
    result: dict[str, Any] = {
        "dated_observations": sum(daily.values()),
        "active_days": len(daily),
        "weekly_windows": [],
        "top_three_days_share": None,
        "peak_day": None,
        "frp": None,
    }
    if daily:
        start, end = min(daily), max(daily)
        overall = sum(daily.values())
        peak_day, peak_total = sorted(
            daily.items(), key=lambda p: (-p[1], p[0])
        )[0]
        result["peak_day"] = {
            "date": peak_day.isoformat(), "count": peak_total,
            "share_percent": round(peak_total / overall * 100, 1),
        }
        result["top_three_days_share"] = round(
            100 * sum(count for _, count in sorted(
                daily.items(), key=lambda p: (-p[1], p[0])
            )[:3]) / overall, 1,
        )
        result["calendar_days"] = (end - start).days + 1
        result["active_day_share"] = round(
            100 * len(daily) / result["calendar_days"], 1,
        )
        # For normal monthly FIRMS extracts: 7-day windows starting at the
        # first observed date. Long histories use larger windows to bound
        # DOCX output without discarding any observations.
        span = result["calendar_days"]
        step = max(7, math.ceil(span / 8))
        date_cursor = start
        while date_cursor <= end:
            limit = min(end, date_cursor + timedelta(days=step - 1))
            group = {
                day: count for day, count in daily.items()
                if date_cursor <= day <= limit
            }
            result["weekly_windows"].append({
                "start": date_cursor.isoformat(),
                "end": limit.isoformat(),
                "count": sum(group.values()),
                "active_days": len(group),
                "share_percent": round(
                    100 * sum(group.values()) / overall, 1,
                ),
            })
            date_cursor = limit + timedelta(days=1)
    if frp_rows:
        values = sorted(row["frp"] for row in frp_rows)
        def quantile(percent):
            # Nearest-rank order statistic is reproducible for small samples.
            return round(values[math.ceil(percent * len(values)) - 1], 2)
        best = sorted(frp_rows, key=lambda row: (
            -row["frp"], row["date"] or "",
            row["longitude"], row["latitude"],
        ))[:3]
        result["frp"] = {
            "count": len(values),
            "median": quantile(.5),
            "p90": quantile(.9),
            "maximum": round(values[-1], 2),
            "top_observations": [
                {**row, "frp": round(row["frp"], 2)} for row in best
            ],
        }
    return result


def build_spatial_report_context(
    rows: list[dict[str, Any]],
    geojson_features: list[dict[str, Any]] | None,
    *,
    source: str = "",
    agricultural_grid_counts: dict[str, dict[str, int]] | None = None,
    grid_surface_counts: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Count real observations covered by installed boundary polygons.

    Boundary overlap is not silently assigned to one area; such records are
    counted as ambiguous. Polygon simplification can affect near-edge points,
    so matches are explicitly described as reference-boundary matches.
    """
    coords = _valid_points(rows)
    if not coords:
        return {"available": False, "total": 0, "source": source}

    west = min(x for x, _ in coords)
    east = max(x for x, _ in coords)
    south = min(y for _, y in coords)
    north = max(y for _, y in coords)
    bbox = [round(west, 5), round(south, 5), round(east, 5), round(north, 5)]
    grids: Counter[tuple[int, int]] = Counter(
        (math.floor(x * 4), math.floor(y * 4)) for x, y in coords
    )
    # Dates are read from the same canonical rows, not from the global
    # database's task-independent observation count. Do not infer a
    # continuous fire from observations recorded on different days.
    grid_dates: dict[tuple[int, int], Counter[str]] = {}
    grid_observations: dict[tuple[int, int], list[tuple[float, float, str]]] = {}
    for row in rows:
        try:
            lon, lat = float(row["longitude"]), float(row["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(lon) and math.isfinite(lat) and
                -180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        cell = (math.floor(lon * 4), math.floor(lat * 4))
        acquired = str(row.get("acquired_date") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", acquired):
            acquired = ""
        # Keep the original observation coordinate. The cell center is
        # artificial and must not be presented as a detected fire location.
        grid_observations.setdefault(cell, []).append((lon, lat, acquired))
        if acquired:
            grid_dates.setdefault(cell, Counter())[acquired] += 1

    ranked_grids = sorted(grids.items(), key=lambda v: (-v[1], v[0]))
    top_grids = []
    for rank, ((cell_x, cell_y), count) in enumerate(ranked_grids[:5], 1):
        cell = (cell_x, cell_y)
        by_date = grid_dates.get(cell, Counter())
        peak_date, peak_count = sorted(
            by_date.items(), key=lambda item: (-item[1], item[0])
        )[0] if by_date else (None, 0)
        observations = grid_observations.get(cell, [])
        on_peak = (
            [point for point in observations if point[2] == peak_date]
            if peak_date else []
        )
        candidates = on_peak or observations
        center_lon = (cell_x + .5) / 4
        center_lat = (cell_y + .5) / 4
        sample = min(
            candidates,
            key=lambda point: (
                (point[0] - center_lon) ** 2
                + (point[1] - center_lat) ** 2,
                point[0], point[1], point[2],
            ),
        )
        actual_observation = {
            "longitude": round(sample[0], 5),
            "latitude": round(sample[1], 5),
            "date": sample[2] or None,
        }
        surfaces = (grid_surface_counts or {}).get(f"{cell_x}:{cell_y}") or {}
        cropland_count = int(surfaces.get("cropland", 0)) + int(
            surfaces.get("mosaic", 0)
        )
        known_surface_count = cropland_count + int(surfaces.get("other", 0))
        top_grids.append({
            "rank": rank,
            "bbox": [cell_x / 4, cell_y / 4, (cell_x + 1) / 4, (cell_y + 1) / 4],
            "center": [round((cell_x + .5) / 4, 4),
                       round((cell_y + .5) / 4, 4)],
            "count": count,
            "share_percent": round(count * 100 / len(coords), 1),
            "active_days": len(by_date),
            "cross_date": len(by_date) >= 2,
            "sample_observation": actual_observation,
            "cropland_background_count": cropland_count,
            "known_surface_count": known_surface_count,
            "agricultural_counts": (
                (agricultural_grid_counts or {}).get(f"{cell_x}:{cell_y}") or {}
            ),
            "peak_date": peak_date,
            "peak_count": peak_count,
        })
    focus = top_grids[0]
    features = []
    polygons = []
    for item in geojson_features or []:
        try:
            geom = shape(item["geometry"])
        except (KeyError, TypeError, ValueError):
            continue
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        raw_name = (item.get("properties") or {}).get("name") or ""
        features.append({"name": display_place(str(raw_name)), "geometry": geom})
        polygons.append(geom)

    matched: Counter[str] = Counter()
    ambiguous = 0
    unmatched = 0
    if polygons:
        tree = STRtree(polygons)
        for lon, lat in coords:
            point = Point(lon, lat)
            hits = [i for i in tree.query(point) if polygons[int(i)].covers(point)]
            if len(hits) != 1:
                if len(hits) > 1:
                    ambiguous += 1
                else:
                    unmatched += 1
                continue
            name = features[int(hits[0])]["name"]
            if name:
                matched[name] += 1
            else:
                unmatched += 1
    else:
        unmatched = len(coords)
    ranking = [
        {"name": name, "count": count, "share_percent": round(100 * count / len(coords), 1)}
        for name, count in sorted(matched.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "available": True,
        "total": len(coords),
        "bbox": bbox,
        "source": str(source or ""),
        "regions": ranking,
        "matched": sum(matched.values()),
        "ambiguous": ambiguous,
        "outside": unmatched,
        "focus_grid": focus,
        "top_grids": top_grids,
        "total_grid_cells": len(grids),
        "top_three_count": sum(item["count"] for item in top_grids[:3]),
        "diagnostics": summarize_observation_diagnostics(rows),
        "map_png": render_spatial_map_png(
            coords, polygons, bbox, hotspot_grids=top_grids,
        ),
        "plotted_points": min(len(coords), 5000),
        "has_geographic_background": bool(polygons),
    }


def render_spatial_map_png(
    coords: list[tuple[float, float]],
    boundaries: list,
    bbox: list[float],
    *,
    width: int = 900,
    height: int = 500,
    focus_bbox: list[float] | None = None,
    hotspot_grids: list[dict[str, Any]] | None = None,
) -> bytes:
    """PNG map, using standard-library rasterization (no EXE dependencies).

    The same WGS84 lon/lat drives the geometry and all observation dots.
    A reproducible max-5000-point subsample only affects visual density.
    """
    background = (246, 250, 252)
    pixels = bytearray(bytes(background) * (width * height))
    west, south, east, north = bbox
    cx, cy = (west + east) / 2, (south + north) / 2
    span_x = max(east - west, .30)
    span_y = max(north - south, .30)
    aspect = (width - 90) / (height - 70)
    if span_x / span_y < aspect:
        span_x = span_y * aspect
    else:
        span_y = span_x / aspect
    west, east = cx - span_x * .57, cx + span_x * .57
    south, north = cy - span_y * .57, cy + span_y * .57

    def xy(point):
        lon, lat = point
        return (
            round(44 + (lon - west) * (width - 88) / (east - west)),
            round(34 + (north - lat) * (height - 68) / (north - south)),
        )

    def pixel(x, y, color):
        if 0 <= x < width and 0 <= y < height:
            i = 3 * (y * width + x)
            pixels[i:i + 3] = bytes(color)

    def segment(a, b, color):
        x0, y0 = xy(a)
        x1, y1 = xy(b)
        # Clip against the image; polygons on distant provinces can have
        # extremely large offscreen pixel coordinates in a local map.
        dx, dy = x1 - x0, y1 - y0
        lo, hi = 0., 1.
        for p, q in ((-dx, x0), (dx, width - 1 - x0),
                     (-dy, y0), (dy, height - 1 - y0)):
            if p == 0:
                if q < 0:
                    return
            else:
                t = q / p
                if p < 0:
                    lo = max(lo, t)
                else:
                    hi = min(hi, t)
        if lo > hi:
            return
        ax, ay = round(x0 + lo * dx), round(y0 + lo * dy)
        bx, by = round(x0 + hi * dx), round(y0 + hi * dy)
        n = max(abs(bx - ax), abs(by - ay), 1)
        for i in range(n + 1):
            pixel(round(ax + (bx - ax) * i / n),
                  round(ay + (by - ay) * i / n), color)

    # Compact built-in ASCII bitmap glyphs keep geographic ticks legible in
    # the bundled Windows EXE without depending on a system font or Matplotlib.
    font = {
        "0": ("01110","10001","10011","10101","11001","10001","01110"),
        "1": ("00100","01100","00100","00100","00100","00100","01110"),
        "2": ("01110","10001","00001","00010","00100","01000","11111"),
        "3": ("11110","00001","00001","01110","00001","00001","11110"),
        "4": ("00010","00110","01010","10010","11111","00010","00010"),
        "5": ("11111","10000","10000","11110","00001","00001","11110"),
        "6": ("00111","01000","10000","11110","10001","10001","01110"),
        "7": ("11111","00001","00010","00100","01000","01000","01000"),
        "8": ("01110","10001","10001","01110","10001","10001","01110"),
        "9": ("01110","10001","10001","01111","00001","00010","11100"),
        ".": ("00000","00000","00000","00000","00000","00110","00110"),
        "E": ("11111","10000","10000","11110","10000","10000","11111"),
        "W": ("10001","10001","10001","10101","10101","11011","10001"),
        "N": ("10001","11001","10101","10011","10001","10001","10001"),
        "S": ("01111","10000","10000","01110","00001","00001","11110"),
    }

    def label(text: str, x: int, y: int):
        for index, ch in enumerate(text):
            for row_index, pattern in enumerate(font.get(ch, ())):
                for col_index, value in enumerate(pattern):
                    if value == "1":
                        pixel(x + index * 6 + col_index, y + row_index,
                              (70, 103, 117))

    def degree(value: float, span: float, positive: str, negative: str):
        digits = 0 if span > 10 else 1 if span > 2 else 2 if span > .2 else 3
        return f"{abs(value):.{digits}f}{negative if value < 0 else positive}"

    # Light coordinate grid supports easy comparison to the exact bbox in text.
    for i in range(7):
        x = 44 + round(i * (width - 88) / 6)
        for y in range(34, height - 34, 3):
            pixel(x, y, (222, 232, 238))
        lon = west + (east - west) * i / 6
        tick = degree(lon, east - west, "E", "W")
        label(tick, max(0, min(width - len(tick) * 6,
                            x - len(tick) * 3)), height - 23)
    for i in range(5):
        y = 34 + round(i * (height - 68) / 4)
        for x in range(44, width - 44, 3):
            pixel(x, y, (222, 232, 238))
        lat = north - (north - south) * i / 4
        tick = degree(lat, north - south, "N", "S")
        label(tick, 2, max(0, min(height - 8, y - 4)))

    def draw_ring(ring):
        seq = list(ring.coords)
        for left, right in zip(seq[:-1], seq[1:]):
            segment(left, right, (82, 140, 164))

    for geom in boundaries:
        gx0, gy0, gx1, gy1 = geom.bounds
        if gx1 < west or gx0 > east or gy1 < south or gy0 > north:
            continue
        polyset = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for polygon in polyset:
            draw_ring(polygon.exterior)
            for ring in polygon.interiors:
                draw_ring(ring)

    stride = max(1, math.ceil(len(coords) / 5000))
    plotted = coords[::stride][:5000]
    for lon, lat in plotted:
        x, y = xy((lon, lat))
        if 44 <= x < width - 44 and 34 <= y < height - 34:
            pixel(x, y, (224, 75, 60))
            pixel(x - 1, y, (233, 118, 91))
            pixel(x + 1, y, (233, 118, 91))

    # The labels 1–5 match the Word review table exactly. Draw real
    # quarter-degree cell edges in WGS84, not parcel or village boundaries.
    # The first cell remains amber; subsequent cells have a thinner blue
    # outline. For overlapping labels, use a fixed short badge above the
    # corresponding center point rather than writing long place names.
    selected_grids = (hotspot_grids or [])[:5]
    if not selected_grids and focus_bbox is not None:
        selected_grids = [{"rank": 1, "bbox": focus_bbox}]
    for index, item in enumerate(selected_grids, 1):
        bounds = item["bbox"]
        fw, fs, fe, fn = bounds
        corners = [(fw, fs), (fe, fs), (fe, fn), (fw, fn), (fw, fs)]
        color = (215, 135, 19) if index == 1 else (77, 142, 174)
        for start, finish in zip(corners[:-1], corners[1:]):
            segment(start, finish, color)

    for index, item in enumerate(selected_grids, 1):
        fw, fs, fe, fn = item["bbox"]
        x, y = xy(((fw + fe) / 2, (fs + fn) / 2))
        if not (48 <= x <= width - 48 and 34 <= y <= height - 40):
            continue
        # White numeric badges remain readable on densely populated dots.
        for dy in range(-7, 8):
            for dx in range(-7, 8):
                if dx * dx + dy * dy <= 49:
                    pixel(x + dx, y + dy, (255, 255, 255))
        number = str(index)
        label(number, x - 2, y - 3)

    # PNG encoder: RGB, eight-bit, no interlace.
    def chunk(kind, content):
        return (
            struct.pack(">I", len(content)) + kind + content
            + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff)
        )
    rows = b"".join(
        b"\x00" + pixels[y * width * 3:(y + 1) * width * 3]
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )
