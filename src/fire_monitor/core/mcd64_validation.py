"""MCD64A1 Burn Date 与 QA GeoTIFF 配对校验。

本模块负责判断两个已经通过单文件基础校验的 GeoTIFF
是否能够安全地进行逐像元联合处理。

当前配对条件包括：
1. 两个文件均能通过基础 GeoTIFF 校验；
2. 产品日期标识一致；
3. 栅格宽高一致；
4. 坐标参考系统一致；
5. GeoTransform 一致；
6. 像元大小一致；
7. 空间范围一致。

通过校验，两个栅格满足当前软件的逐像元配准要求
"""

from __future__ import annotations

from math import isclose
from pathlib import Path
from typing import Any

from fire_monitor.core.file_validation import (
    ValidationResult,
    validate_mcd64_geotiff,
)


FLOAT_TOLERANCE = 1e-12


def _numbers_close(
    left: float,
    right: float,
) -> bool:
    """判断两个空间参数是否在允许的浮点误差内一致。"""

    return isclose(
        float(left),
        float(right),
        rel_tol=0.0,
        abs_tol=FLOAT_TOLERANCE,
    )


def _geotransforms_match(
    left: list[float],
    right: list[float],
) -> bool:
    """逐项比较两个 GeoTransform。"""

    if len(left) != 6 or len(right) != 6:
        return False

    return all(
        _numbers_close(a, b)
        for a, b in zip(left, right)
    )


def _raster_extent(
    *,
    width: int,
    height: int,
    geotransform: list[float],
) -> dict[str, float]:
    """计算无旋转北向上栅格的空间范围。"""

    x_origin = float(geotransform[0])
    x_step = float(geotransform[1])
    y_origin = float(geotransform[3])
    y_step = float(geotransform[5])

    x_end = x_origin + width * x_step
    y_end = y_origin + height * y_step

    return {
        "west": min(x_origin, x_end),
        "south": min(y_origin, y_end),
        "east": max(x_origin, x_end),
        "north": max(y_origin, y_end),
    }


def _extents_match(
    left: dict[str, float],
    right: dict[str, float],
) -> bool:
    """比较两个栅格空间范围。"""

    keys = {
        "west",
        "south",
        "east",
        "north",
    }

    return all(
        _numbers_close(
            left[key],
            right[key],
        )
        for key in keys
    )


def validate_mcd64_pair(
    burn_date_path: str | Path,
    qa_path: str | Path,
) -> ValidationResult:
    """校验 Burn Date 与 QA 是否能够逐像元配对。

    两个文件必须具有相同：
    - AYYYYDDD 产品日期；
    - 宽度和高度；
    - CRS；
    - GeoTransform；
    - 像元大小；
    - 空间范围。
    """

    burn_result = validate_mcd64_geotiff(
        burn_date_path,
        file_role="mcd64_burn_date",
    )

    if not burn_result.accepted:
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 文件基础校验失败："
                + burn_result.message
            ),
            metadata={
                "burn_date_validation": {
                    "status": burn_result.status,
                    "message": burn_result.message,
                    "metadata": burn_result.metadata,
                }
            },
        )

    qa_result = validate_mcd64_geotiff(
        qa_path,
        file_role="mcd64_qa",
    )

    if not qa_result.accepted:
        return ValidationResult(
            status="invalid",
            message=(
                "QA 文件基础校验失败："
                + qa_result.message
            ),
            metadata={
                "burn_date_validation": {
                    "status": burn_result.status,
                    "message": burn_result.message,
                    "metadata": burn_result.metadata,
                },
                "qa_validation": {
                    "status": qa_result.status,
                    "message": qa_result.message,
                    "metadata": qa_result.metadata,
                },
            },
        )

    burn = burn_result.metadata
    qa = qa_result.metadata

    # 当前算法只读取第一波段。
    # 为防止误把多波段文件当作单层产品处理，
    # 配对阶段明确要求单波段 GeoTIFF。
    if (
        burn["band_count"] != 1
        or qa["band_count"] != 1
    ):
        return ValidationResult(
            status="invalid",
            message=(
                "当前版本要求 Burn Date 和 QA "
                "均为单波段 GeoTIFF。"
            ),
            metadata={
                "burn_date_band_count": (
                    burn["band_count"]
                ),
                "qa_band_count": qa["band_count"],
            },
        )

    if (
        burn["year"] != qa["year"]
        or burn["month_start_doy"]
        != qa["month_start_doy"]
    ):
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 与 QA 文件的 "
                "AYYYYDDD 产品日期不一致。"
            ),
            metadata={
                "burn_date_product_date": {
                    "year": burn["year"],
                    "month_start_doy": (
                        burn["month_start_doy"]
                    ),
                },
                "qa_product_date": {
                    "year": qa["year"],
                    "month_start_doy": (
                        qa["month_start_doy"]
                    ),
                },
            },
        )

    if (
        burn["width"] != qa["width"]
        or burn["height"] != qa["height"]
    ):
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 与 QA 栅格尺寸不一致。"
            ),
            metadata={
                "burn_date_size": [
                    burn["width"],
                    burn["height"],
                ],
                "qa_size": [
                    qa["width"],
                    qa["height"],
                ],
            },
        )

    if burn["crs"] != qa["crs"]:
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 与 QA "
                "坐标参考系统不一致。"
            ),
            metadata={
                "burn_date_crs": burn["crs"],
                "qa_crs": qa["crs"],
            },
        )

    burn_gt = [
        float(value)
        for value in burn["geotransform"]
    ]

    qa_gt = [
        float(value)
        for value in qa["geotransform"]
    ]

    if not _geotransforms_match(
        burn_gt,
        qa_gt,
    ):
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 与 QA "
                "GeoTransform 不一致，"
                "不能安全进行逐像元配对。"
            ),
            metadata={
                "burn_date_geotransform": burn_gt,
                "qa_geotransform": qa_gt,
            },
        )

    burn_pixel_size = {
        "x": abs(burn_gt[1]),
        "y": abs(burn_gt[5]),
    }

    qa_pixel_size = {
        "x": abs(qa_gt[1]),
        "y": abs(qa_gt[5]),
    }

    if not (
        _numbers_close(
            burn_pixel_size["x"],
            qa_pixel_size["x"],
        )
        and _numbers_close(
            burn_pixel_size["y"],
            qa_pixel_size["y"],
        )
    ):
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 与 QA "
                "像元分辨率不一致。"
            ),
            metadata={
                "burn_date_pixel_size": (
                    burn_pixel_size
                ),
                "qa_pixel_size": (
                    qa_pixel_size
                ),
            },
        )

    burn_extent = _raster_extent(
        width=int(burn["width"]),
        height=int(burn["height"]),
        geotransform=burn_gt,
    )

    qa_extent = _raster_extent(
        width=int(qa["width"]),
        height=int(qa["height"]),
        geotransform=qa_gt,
    )

    if not _extents_match(
        burn_extent,
        qa_extent,
    ):
        return ValidationResult(
            status="invalid",
            message=(
                "Burn Date 与 QA "
                "空间覆盖范围不一致。"
            ),
            metadata={
                "burn_date_extent": (
                    burn_extent
                ),
                "qa_extent": qa_extent,
            },
        )

    metadata: dict[str, Any] = {
        "year": burn["year"],
        "month_start_doy": (
            burn["month_start_doy"]
        ),
        "width": burn["width"],
        "height": burn["height"],
        "crs": burn["crs"],
        "geotransform": burn_gt,
        "pixel_size": burn_pixel_size,
        "extent": burn_extent,
        "burn_date_data_type": (
            burn["gdal_data_type"]
        ),
        "qa_data_type": (
            qa["gdal_data_type"]
        ),
    }

    return ValidationResult(
        status="valid",
        message=(
            "Burn Date 与 QA GeoTIFF "
            "配对一致性校验通过。"
        ),
        metadata=metadata,
    )