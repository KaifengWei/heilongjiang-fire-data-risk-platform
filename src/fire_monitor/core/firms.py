"""FIRMS 主动火点数据的规范化与可选在线下载。"""

from __future__ import annotations

import hashlib
import os
from datetime import date, timedelta
from io import StringIO
from typing import Any, Iterator

import pandas as pd
import requests


FIRMS_AREA_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def _column_lookup(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(column).strip().lower().lstrip("\ufeff"): column for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def _as_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def firms_quality_pass(instrument: str | None, confidence: Any) -> bool:
    """沿用当前项目已记录的质量筛选规则。

    VIIRS：confidence 为 n / h；MODIS：confidence 数值不低于 30。
    缺少仪器或置信度时不擅自判为高质量。
    """
    instrument_text = (instrument or "").strip().upper()
    confidence_text = _as_text(confidence)
    if instrument_text == "VIIRS":
        return (confidence_text or "").lower() in {"n", "h"}
    if instrument_text == "MODIS":
        value = _as_float(confidence)
        return value is not None and value >= 30
    return False


def normalized_firms_rows(
    frame: pd.DataFrame,
    *,
    firms_source: str,
    quality_only: bool,
    region_column: str | None = None,
) -> Iterator[dict[str, Any]]:
    latitude_col = _column_lookup(frame, ["latitude", "lat"])
    longitude_col = _column_lookup(frame, ["longitude", "lon", "lng"])
    date_col = _column_lookup(frame, ["acq_date", "date", "日期"])
    time_col = _column_lookup(frame, ["acq_time", "time", "时间"])
    instrument_col = _column_lookup(frame, ["instrument", "传感器"])
    satellite_col = _column_lookup(frame, ["satellite", "卫星"])
    confidence_col = _column_lookup(frame, ["confidence", "置信度"])
    frp_col = _column_lookup(frame, ["frp"])
    scan_col = _column_lookup(frame, ["scan"])
    track_col = _column_lookup(frame, ["track"])
    if not latitude_col or not longitude_col or not date_col:
        raise ValueError("FIRMS CSV 至少需要 latitude、longitude、acq_date 三列。")

    for raw in frame.to_dict(orient="records"):
        latitude = _as_float(raw.get(latitude_col))
        longitude = _as_float(raw.get(longitude_col))
        parsed_date = pd.to_datetime(raw.get(date_col), errors="coerce")
        if latitude is None or longitude is None or pd.isna(parsed_date):
            continue
        instrument = _as_text(raw.get(instrument_col)) if instrument_col else None
        satellite = _as_text(raw.get(satellite_col)) if satellite_col else None
        confidence = _as_text(raw.get(confidence_col)) if confidence_col else None
        accepted = firms_quality_pass(instrument, confidence)
        if quality_only and not accepted:
            continue
        acquired_date = parsed_date.date().isoformat()
        acquired_time = _as_text(raw.get(time_col)) if time_col else None
        key_parts = [
            firms_source,
            acquired_date,
            acquired_time or "",
            f"{latitude:.6f}",
            f"{longitude:.6f}",
            instrument or "",
            satellite or "",
        ]
        yield {
            "dedupe_key": hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest(),
            "acquired_date": acquired_date,
            "acquired_time": acquired_time,
            "latitude": latitude,
            "longitude": longitude,
            "firms_source": firms_source,
            "instrument": instrument,
            "satellite": satellite,
            "confidence": confidence,
            "frp": _as_float(raw.get(frp_col)) if frp_col else None,
            "scan": _as_float(raw.get(scan_col)) if scan_col else None,
            "track": _as_float(raw.get(track_col)) if track_col else None,
            "quality_rule": "VIIRS:n/h; MODIS:confidence>=30" if quality_only else "未执行质量筛选",
            "source_region_name": _as_text(raw.get(region_column)) if region_column else None,
        }


def split_firms_date_ranges(start: date, end: date, max_days: int = 5) -> Iterator[tuple[date, int]]:
    """FIRMS Area API 按不超过 5 天的小批次请求，避免超出接口约束。"""
    current = start
    while current <= end:
        days = min(max_days, (end - current).days + 1)
        yield current, days
        current += timedelta(days=days)


def fetch_firms_area_csv(
    *,
    source: str,
    bbox: str,
    start: date,
    end: date,
    map_key: str | None = None,
    timeout_seconds: int = 60,
) -> pd.DataFrame:
    """调用 FIRMS Area API，返回未改写的官方 CSV 记录。

    MAP_KEY 默认只从环境变量 ``FIRMS_MAP_KEY`` 读取。调用方应把密钥保存在
    本机环境或未提交的 .env 文件中，不能提交到 Git 仓库。
    """
    key = map_key or os.environ.get("FIRMS_MAP_KEY")
    if not key:
        raise RuntimeError("未找到 FIRMS_MAP_KEY。请先在本机环境变量中设置 MAP_KEY。")
    pieces: list[pd.DataFrame] = []
    for block_start, days in split_firms_date_ranges(start, end):
        url = f"{FIRMS_AREA_API}/{key}/{source}/{bbox}/{days}/{block_start.isoformat()}"
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        text = response.text.strip()
        if text and not text.lower().startswith("no data"):
            pieces.append(pd.read_csv(StringIO(text)))
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True)
