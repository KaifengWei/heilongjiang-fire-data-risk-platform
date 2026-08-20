"""MCD64 火烧迹地 TIF 读取与面积计算。

首版只接受北向上的 EPSG:4326（经纬度）GeoTIFF。对于当前已核验的
MCD64monthly *.burndate.tif，这样可以按各纬度行的实际球面面积计算，
不会把经纬度网格机械写成 0.25 km² 固定像元。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from fire_monitor.core.geography import RegionIndex


EARTH_RADIUS_M = 6_371_007.181
MCD64_NAME_PATTERN = re.compile(r"A(?P<year>\d{4})(?P<doy>\d{3})", re.IGNORECASE)


@dataclass(frozen=True)
class Mcd64Metadata:
    source_path: Path
    product: str
    year: int
    month_start_doy: int
    raster_name: str
    raster_sha256: str


def parse_mcd64_metadata(path: str | Path, product: str = "MCD64A1") -> Mcd64Metadata:
    source_path = Path(path)
    match = MCD64_NAME_PATTERN.search(source_path.name)
    if not match:
        raise ValueError("无法从文件名识别 AYYYYDDD；请使用 MCD64 月度 burndate 文件名。")
    year = int(match.group("year"))
    month_start_doy = int(match.group("doy"))
    try:
        date(year, 1, 1) + timedelta(days=month_start_doy - 1)
    except ValueError as exc:
        raise ValueError("文件名中的年积日无效。") from exc
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return Mcd64Metadata(
        source_path=source_path,
        product=product,
        year=year,
        month_start_doy=month_start_doy,
        raster_name=source_path.name,
        raster_sha256=digest,
    )


def spherical_geographic_cell_area_km2(
    lon_step_degrees: float, north_latitude: float, south_latitude: float
) -> float:
    """计算经纬度栅格单元在球面上的面积。"""
    lon_step_radians = np.deg2rad(abs(lon_step_degrees))
    north = np.deg2rad(north_latitude)
    south = np.deg2rad(south_latitude)
    return float(EARTH_RADIUS_M**2 * lon_step_radians * abs(np.sin(north) - np.sin(south)) / 1_000_000)


def _load_gdal() -> Any:
    try:
        from osgeo import gdal  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "未检测到 GDAL。请使用 environment.yml 创建 Conda 环境后再导入 MCD64 TIF。"
        ) from exc
    return gdal


def _month_doy_range(year: int, start_doy: int) -> tuple[int, int]:
    start_date = date(year, 1, 1) + timedelta(days=start_doy - 1)
    if start_date.month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, start_date.month + 1, 1)
    end_date = next_month - timedelta(days=1)
    return start_doy, int(end_date.strftime("%j"))


def extract_mcd64_burned_pixels(
    path: str | Path,
    *,
    region_index: RegionIndex,
    product: str = "MCD64A1",
    qa_path: str | Path | None = None,
    chunk_rows: int = 256,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """从月度 ``burndate`` TIF 提取已落入导入行政区的烧毁像元。"""
    metadata = parse_mcd64_metadata(path, product=product)
    gdal = _load_gdal()
    dataset = gdal.Open(str(metadata.source_path))
    if dataset is None:
        raise RuntimeError(f"无法打开 TIF：{metadata.source_path}")
    qa_dataset = gdal.Open(str(qa_path)) if qa_path else None
    if qa_path and qa_dataset is None:
        raise RuntimeError(f"无法打开 QA TIF：{qa_path}")
    if qa_dataset and (qa_dataset.RasterXSize != dataset.RasterXSize or qa_dataset.RasterYSize != dataset.RasterYSize):
        raise ValueError("QA TIF 与 burndate TIF 尺寸不一致。")

    geotransform = dataset.GetGeoTransform(can_return_null=True)
    projection = dataset.GetProjectionRef() or ""
    if geotransform is None:
        raise ValueError("TIF 缺少地理变换参数。")
    if abs(geotransform[2]) > 1e-12 or abs(geotransform[4]) > 1e-12:
        raise ValueError("首版只支持无旋转的北向上栅格。")
    if "GEOGCS" not in projection.upper() and "EPSG\",\"4326" not in projection.upper():
        raise ValueError("首版只支持经纬度（EPSG:4326）GeoTIFF；请先重投影或扩展算法。")

    x_origin, x_step, _, y_origin, _, y_step = geotransform
    if x_step == 0 or y_step == 0:
        raise ValueError("TIF 像元大小无效。")
    width, height = dataset.RasterXSize, dataset.RasterYSize
    band = dataset.GetRasterBand(1)
    qa_band = qa_dataset.GetRasterBand(1) if qa_dataset else None
    valid_start, valid_end = _month_doy_range(metadata.year, metadata.month_start_doy)
    rows: list[dict[str, Any]] = []
    outside_month = 0
    assigned = 0

    for row_start in range(0, height, chunk_rows):
        read_rows = min(chunk_rows, height - row_start)
        values = band.ReadAsArray(0, row_start, width, read_rows)
        qa_values = qa_band.ReadAsArray(0, row_start, width, read_rows) if qa_band else None
        positive_indices = np.argwhere(values > 0)
        for local_row, column in positive_indices:
            doy = int(values[local_row, column])
            if doy < valid_start or doy > valid_end:
                outside_month += 1
                continue
            global_row = row_start + int(local_row)
            longitude = x_origin + (int(column) + 0.5) * x_step
            latitude = y_origin + (global_row + 0.5) * y_step
            region_name = region_index.locate(longitude, latitude)
            if not region_name:
                continue
            north = y_origin + global_row * y_step
            south = y_origin + (global_row + 1) * y_step
            cell_area = spherical_geographic_cell_area_km2(x_step, north, south)
            burned_date = date(metadata.year, 1, 1) + timedelta(days=doy - 1)
            key_parts = [
                metadata.raster_sha256,
                f"{longitude:.8f}",
                f"{latitude:.8f}",
                burned_date.isoformat(),
            ]
            rows.append(
                {
                    "dedupe_key": hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest(),
                    "burned_date": burned_date.isoformat(),
                    "doy": doy,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "region_name": region_name,
                    "cell_area_km2": cell_area,
                    "source_product": metadata.product,
                    "raster_name": metadata.raster_name,
                    "qa_value": int(qa_values[local_row, column]) if qa_values is not None else None,
                }
            )
            assigned += 1

    meta = {
        "product": metadata.product,
        "raster_name": metadata.raster_name,
        "raster_sha256": metadata.raster_sha256,
        "year": metadata.year,
        "month_start_doy": metadata.month_start_doy,
        "valid_doy_range": [valid_start, valid_end],
        "qa_path": str(qa_path) if qa_path else None,
        "qa_available": qa_path is not None,
        "positive_pixels_in_regions": assigned,
        "positive_values_outside_expected_month": outside_month,
        "area_method": "球面经纬度网格实际面积求和",
    }
    return rows, meta
