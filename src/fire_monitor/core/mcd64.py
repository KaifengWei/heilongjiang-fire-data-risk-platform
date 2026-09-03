"""MCD64 火烧迹地 TIF 读取与面积计算。

首版只接受北向上的 EPSG:4326（经纬度）GeoTIFF。
可以按各纬度行的实际球面面积计算，不会把经纬度网格机械写成 0.25 km² 固定像元。
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from fire_monitor.core.geography import RegionIndex
from fire_monitor.core.mcd64_qa import (
    evaluate_burned_candidate_qa,
)
from fire_monitor.core.mcd64_validation import (
    validate_mcd64_pair,
)

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


def canonical_burned_pixel_key(
    *,
    source_product: str,
    burned_date: str,
    longitude: float,
    latitude: float,
    cell_area_km2: float,
) -> str:
    """生成烧毁像元的规范身份键。

    该身份描述的是烧毁像元本身，
    不包含 GeoTIFF 文件 SHA256。

    因此：
    - 同一产品、同一日期、同一网格像元，
      即使 GeoTIFF 被重新压缩或重新导出，
      仍视为同一烧毁像元；
    - 像元面积不同则不视为同一网格单元。
    """

    parts = [
        str(source_product).strip().upper(),
        str(burned_date),
        f"{float(longitude):.8f}",
        f"{float(latitude):.8f}",
        f"{float(cell_area_km2):.8f}",
    ]

    return hashlib.sha256(
        "|".join(parts).encode(
            "utf-8"
        )
    ).hexdigest()

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
            "未检测到 GDAL。请使用 environment.yml "
            "创建 Conda 环境后再导入 MCD64 TIF。"
        ) from exc

    gdal.UseExceptions()

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
    qa_policy: str = "standard",
    chunk_rows: int = 256,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    """提取通过当前质量策略且落入行政区的烧毁像元。

    当前处理顺序：

    1. Burn Date > 0；
    2. Burn Date 必须落在产品月份范围；
    3. 若提供 QA，则执行 QA bit 判断；
    4. 执行行政区落区；
    5. 计算经纬度栅格实际球面面积。

    qa_path=None 时保留旧兼容行为，不执行 QA 筛选。
    正式任务处理阶段后续将要求必须提供 QA。
    """

    metadata = parse_mcd64_metadata(
        path,
        product=product,
    )

    if qa_path is not None:
        pair_result = (
            validate_mcd64_pair(
                path,
                qa_path,
            )
        )

        if not pair_result.accepted:
            raise ValueError(
                "MCD64A1 Burn Date / QA "
                "配对校验失败："
                + pair_result.message
            )

    gdal = _load_gdal()

    try:
        dataset = gdal.Open(
            str(metadata.source_path),
            gdal.GA_ReadOnly,
        )
    except RuntimeError as exc:
        raise RuntimeError(
            f"无法打开 Burn Date TIF："
            f"{metadata.source_path}"
        ) from exc

    if dataset is None:
        raise RuntimeError(
            f"无法打开 Burn Date TIF："
            f"{metadata.source_path}"
        )

    qa_dataset = None

    if qa_path is not None:
        try:
            qa_dataset = gdal.Open(
                str(qa_path),
                gdal.GA_ReadOnly,
            )
        except RuntimeError as exc:
            dataset = None
            raise RuntimeError(
                f"无法打开 QA TIF：{qa_path}"
            ) from exc

        if qa_dataset is None:
            dataset = None
            raise RuntimeError(
                f"无法打开 QA TIF：{qa_path}"
            )

    try:
        geotransform = (
            dataset.GetGeoTransform(
                can_return_null=True
            )
        )

        projection = (
            dataset.GetProjectionRef()
            or ""
        )

        if geotransform is None:
            raise ValueError(
                "TIF 缺少地理变换参数。"
            )

        if (
            abs(geotransform[2])
            > 1e-12
            or abs(geotransform[4])
            > 1e-12
        ):
            raise ValueError(
                "当前版本只支持无旋转的"
                "北向上栅格。"
            )

        if (
            "GEOGCS"
            not in projection.upper()
            and
            'EPSG","4326'
            not in projection.upper()
        ):
            raise ValueError(
                "当前版本只支持经纬度"
                "（EPSG:4326）GeoTIFF。"
            )

        (
            x_origin,
            x_step,
            _,
            y_origin,
            _,
            y_step,
        ) = geotransform

        if (
            x_step == 0
            or y_step == 0
        ):
            raise ValueError(
                "TIF 像元大小无效。"
            )

        width = int(
            dataset.RasterXSize
        )

        height = int(
            dataset.RasterYSize
        )

        band = (
            dataset.GetRasterBand(1)
        )

        if band is None:
            raise RuntimeError(
                "无法读取 Burn Date 第一波段。"
            )

        qa_band = (
            qa_dataset.GetRasterBand(1)
            if qa_dataset is not None
            else None
        )

        if (
            qa_dataset is not None
            and qa_band is None
        ):
            raise RuntimeError(
                "无法读取 QA 第一波段。"
            )

        (
            valid_start,
            valid_end,
        ) = _month_doy_range(
            metadata.year,
            metadata.month_start_doy,
        )

        rows: list[
            dict[str, Any]
        ] = []

        positive_candidates = 0
        outside_month = 0

        qa_evaluated = 0
        qa_rejected = 0

        qa_rejection_counts: Counter[
            str
        ] = Counter()

        shortened_mapping_pixels = 0
        contextual_relabeling_pixels = 0

        outside_regions = 0

        accepted_pixels = 0
        accepted_area_km2 = 0.0

        for row_start in range(
            0,
            height,
            chunk_rows,
        ):
            read_rows = min(
                chunk_rows,
                height - row_start,
            )

            values = band.ReadAsArray(
                0,
                row_start,
                width,
                read_rows,
            )

            if values is None:
                raise RuntimeError(
                    "读取 Burn Date 栅格失败。"
                )

            qa_values = None

            if qa_band is not None:
                qa_values = (
                    qa_band.ReadAsArray(
                        0,
                        row_start,
                        width,
                        read_rows,
                    )
                )

                if qa_values is None:
                    raise RuntimeError(
                        "读取 QA 栅格失败。"
                    )

            positive_indices = (
                np.argwhere(
                    values > 0
                )
            )

            positive_candidates += int(
                len(positive_indices)
            )

            for (
                local_row,
                column,
            ) in positive_indices:
                doy = int(
                    values[
                        local_row,
                        column,
                    ]
                )

                # Burn Date 必须属于当前
                # 月度产品覆盖月份。
                if (
                    doy < valid_start
                    or doy > valid_end
                ):
                    outside_month += 1
                    continue

                qa_value: int | None = None
                qa_decision = None

                if qa_values is not None:
                    qa_value = int(
                        qa_values[
                            local_row,
                            column,
                        ]
                    )

                    qa_decision = (
                        evaluate_burned_candidate_qa(
                            qa_value,
                            policy=qa_policy,
                        )
                    )

                    qa_evaluated += 1

                    decoded = (
                        qa_decision.decoded
                    )

                    if (
                        decoded
                        .shortened_mapping_period
                    ):
                        shortened_mapping_pixels += 1

                    if (
                        decoded
                        .contextually_relabeled
                    ):
                        contextual_relabeling_pixels += 1

                    if not qa_decision.accepted:
                        qa_rejected += 1

                        if not decoded.is_land:
                            qa_rejection_counts[
                                "water"
                            ] += 1

                        if (
                            not decoded
                            .has_valid_data
                        ):
                            qa_rejection_counts[
                                "insufficient_valid_data"
                            ] += 1

                        if (
                            decoded
                            .spare_bit_set
                        ):
                            qa_rejection_counts[
                                "spare_bit_set"
                            ] += 1

                        if (
                            decoded
                            .special_condition_code
                            != 0
                        ):
                            qa_rejection_counts[
                                "special_condition"
                            ] += 1

                        if (
                            qa_policy
                            == "strict"
                            and decoded
                            .shortened_mapping_period
                        ):
                            qa_rejection_counts[
                                "shortened_mapping_period"
                            ] += 1

                        continue

                global_row = (
                    row_start
                    + int(local_row)
                )

                column_index = int(
                    column
                )

                longitude = (
                    x_origin
                    + (
                        column_index
                        + 0.5
                    )
                    * x_step
                )

                latitude = (
                    y_origin
                    + (
                        global_row
                        + 0.5
                    )
                    * y_step
                )

                region_name = (
                    region_index.locate(
                        longitude,
                        latitude,
                    )
                )

                if not region_name:
                    outside_regions += 1
                    continue

                north = (
                    y_origin
                    + global_row
                    * y_step
                )

                south = (
                    y_origin
                    + (
                        global_row + 1
                    )
                    * y_step
                )

                cell_area = (
                    spherical_geographic_cell_area_km2(
                        x_step,
                        north,
                        south,
                    )
                )

                burned_date = (
                    date(
                        metadata.year,
                        1,
                        1,
                    )
                    + timedelta(
                        days=doy - 1
                    )
                )

                key_parts = [
                    metadata.raster_sha256,
                    f"{longitude:.8f}",
                    f"{latitude:.8f}",
                    burned_date.isoformat(),
                ]

                canonical_key = (
                    canonical_burned_pixel_key(
                        source_product=(
                            metadata.product
                        ),
                        burned_date=(
                            burned_date.isoformat()
                        ),
                        longitude=float(
                            longitude
                        ),
                        latitude=float(
                            latitude
                        ),
                        cell_area_km2=(
                            cell_area
                        ),
                    )
                )

                row_data = {
                    "dedupe_key": (
                        hashlib.sha256(
                            "|".join(
                                key_parts
                            ).encode(
                                "utf-8"
                            )
                        ).hexdigest()
                    ),
                    "canonical_key": (
                        canonical_key
                    ),
                    "burned_date": (
                        burned_date
                        .isoformat()
                    ),
                    "doy": doy,
                    "latitude": float(
                        latitude
                    ),
                    "longitude": float(
                        longitude
                    ),
                    "region_name": (
                        region_name
                    ),
                    "cell_area_km2": (
                        cell_area
                    ),
                    "source_product": (
                        metadata.product
                    ),
                    "raster_name": (
                        metadata.raster_name
                    ),
                    "qa_value": (
                        qa_value
                    ),
                }

                if qa_decision is not None:
                    row_data[
                        "qa_policy"
                    ] = qa_policy

                    row_data[
                        "qa_shortened_mapping_period"
                    ] = (
                        qa_decision
                        .decoded
                        .shortened_mapping_period
                    )

                    row_data[
                        "qa_contextually_relabeled"
                    ] = (
                        qa_decision
                        .decoded
                        .contextually_relabeled
                    )

                rows.append(
                    row_data
                )

                accepted_pixels += 1
                accepted_area_km2 += (
                    cell_area
                )

        meta = {
            "product": (
                metadata.product
            ),
            "raster_name": (
                metadata.raster_name
            ),
            "raster_sha256": (
                metadata.raster_sha256
            ),
            "year": metadata.year,
            "month_start_doy": (
                metadata.month_start_doy
            ),
            "valid_doy_range": [
                valid_start,
                valid_end,
            ],

            "qa_path": (
                str(qa_path)
                if qa_path
                else None
            ),

            "qa_available": (
                qa_path is not None
            ),

            "qa_applied": (
                qa_path is not None
            ),

            "qa_policy": (
                qa_policy
                if qa_path is not None
                else None
            ),

            "positive_burn_date_pixels": (
                positive_candidates
            ),

            "positive_values_outside_expected_month": (
                outside_month
            ),

            "qa_evaluated_pixels": (
                qa_evaluated
            ),

            "qa_rejected_pixels": (
                qa_rejected
            ),

            "qa_rejection_counts": (
                dict(
                    qa_rejection_counts
                )
            ),

            "qa_shortened_mapping_period_pixels": (
                shortened_mapping_pixels
            ),

            "qa_contextually_relabeled_pixels": (
                contextual_relabeling_pixels
            ),

            "outside_configured_regions": (
                outside_regions
            ),

            # 保留旧字段名，
            # 兼容原有调用方。
            "positive_pixels_in_regions": (
                accepted_pixels
            ),

            "accepted_burned_pixels": (
                accepted_pixels
            ),

            "accepted_burned_area_km2": (
                round(
                    accepted_area_km2,
                    6,
                )
            ),

            "area_method": (
                "球面经纬度网格实际面积求和"
            ),
        }

        return rows, meta

    finally:
        qa_dataset = None
        dataset = None
