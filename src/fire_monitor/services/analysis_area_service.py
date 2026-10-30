"""User-declared analysis areas, separate from verified administrative boundaries."""
from __future__ import annotations

import math
from typing import Any

DEFAULT_LABEL = "本次上传数据范围"


def normalize_area_label(value: str | None) -> str:
    label = str(value or "").strip()
    if len(label) > 80:
        raise ValueError("区域名称不能超过80个字符。")
    if any(ord(ch) < 32 for ch in label):
        raise ValueError("区域名称包含非法控制字符。")
    return label or DEFAULT_LABEL


def parse_request_bbox(value: str | None) -> list[float] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    pieces = [p.strip() for p in raw.split(",")]
    if len(pieces) != 4:
        raise ValueError("下载范围应为4个数字：最小经度,最小纬度,最大经度,最大纬度。")
    try:
        west, south, east, north = (float(p) for p in pieces)
    except ValueError as exc:
        raise ValueError("下载范围只能填写经纬度数字。") from exc
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise ValueError("下载范围包含无效数字。")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("下载范围顺序或经纬度超出有效范围。")
    return [west, south, east, north]


def within_bbox(longitude: float, latitude: float, bbox: list[float]) -> bool:
    west, south, east, north = bbox
    return west <= longitude <= east and south <= latitude <= north


def observation_bbox(rows: list[dict[str, Any]]) -> list[float] | None:
    coordinates = []
    for row in rows:
        try:
            lon = float(row["longitude"])
            lat = float(row["latitude"])
        except (ValueError, TypeError, KeyError):
            continue
        if math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90:
            coordinates.append((lon, lat))
    if not coordinates:
        return None
    return [
        round(min(item[0] for item in coordinates), 5),
        round(min(item[1] for item in coordinates), 5),
        round(max(item[0] for item in coordinates), 5),
        round(max(item[1] for item in coordinates), 5),
    ]
