"""用户输入文件的基础合同校验。

本模块负责判断一个输入文件是否满足当前软件版本
是进入后续处理流程的基本条件。

这里的“valid”表示满足本软件当前输入合同，
不代表数据来源真实性、遥感产品精度或官方有效认证。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


SUPPORTED_FILE_ROLES = {
    "firms_csv",
    "mcd64_burn_date",
    "mcd64_qa",
}


MCD64_NAME_PATTERN = re.compile(
    r"A(?P<year>\d{4})(?P<doy>\d{3})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationResult:
    """输入文件基础校验结果。"""

    status: str
    message: str
    metadata: dict[str, Any]

    @property
    def accepted(self) -> bool:
        return self.status in {
            "valid",
            "valid_with_warnings",
        }


def _normalize_header(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .lstrip("\ufeff")
    )


def _find_column(
    fieldnames: list[str],
    candidates: set[str],
) -> str | None:
    lookup = {
        _normalize_header(name): name
        for name in fieldnames
    }

    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]

    return None


def _is_valid_coordinate(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> bool:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return False

    return minimum <= number <= maximum


def _is_valid_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return False

    return True


def validate_firms_csv(
    path: str | Path,
) -> ValidationResult:
    """校验 FIRMS CSV 的基本字段和逐行基础值。

    当前最低字段合同与项目现有 FIRMS 解析器保持一致：
    latitude、longitude、acq_date。

    instrument 和 confidence 不作为最低格式条件，
    但缺少它们时无法可靠执行当前项目的质量筛选，
    因此返回警告。
    """

    source_path = Path(path)

    if source_path.suffix.lower() != ".csv":
        return ValidationResult(
            status="invalid",
            message="FIRMS 输入文件必须为 CSV。",
            metadata={},
        )

    if not source_path.is_file():
        return ValidationResult(
            status="invalid",
            message="FIRMS CSV 文件不存在。",
            metadata={},
        )

    if source_path.stat().st_size == 0:
        return ValidationResult(
            status="invalid",
            message="FIRMS CSV 文件为空。",
            metadata={
                "size_bytes": 0,
            },
        )

    try:
        handle = source_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        )
    except OSError as exc:
        return ValidationResult(
            status="invalid",
            message=f"无法读取 FIRMS CSV：{exc}",
            metadata={},
        )

    with handle:
        try:
            reader = csv.DictReader(handle)
            raw_fieldnames = reader.fieldnames
        except csv.Error as exc:
            return ValidationResult(
                status="invalid",
                message=f"CSV 表头解析失败：{exc}",
                metadata={},
            )

        if not raw_fieldnames:
            return ValidationResult(
                status="invalid",
                message="FIRMS CSV 缺少表头。",
                metadata={},
            )

        fieldnames = [
            str(name)
            for name in raw_fieldnames
            if name is not None
        ]

        latitude_col = _find_column(
            fieldnames,
            {"latitude", "lat"},
        )
        longitude_col = _find_column(
            fieldnames,
            {"longitude", "lon", "lng"},
        )
        date_col = _find_column(
            fieldnames,
            {"acq_date", "date", "日期"},
        )

        instrument_col = _find_column(
            fieldnames,
            {"instrument", "传感器"},
        )
        confidence_col = _find_column(
            fieldnames,
            {"confidence", "置信度"},
        )

        missing_required: list[str] = []

        if latitude_col is None:
            missing_required.append("latitude")

        if longitude_col is None:
            missing_required.append("longitude")

        if date_col is None:
            missing_required.append("acq_date")

        if missing_required:
            return ValidationResult(
                status="invalid",
                message=(
                    "FIRMS CSV 缺少必要字段："
                    + ", ".join(missing_required)
                ),
                metadata={
                    "columns": fieldnames,
                    "missing_required": missing_required,
                },
            )

        total_rows = 0
        invalid_rows = 0

        try:
            for row in reader:
                if not any(
                    str(value).strip()
                    for value in row.values()
                    if value is not None
                ):
                    continue

                total_rows += 1

                latitude_valid = _is_valid_coordinate(
                    row.get(latitude_col),
                    minimum=-90.0,
                    maximum=90.0,
                )

                longitude_valid = _is_valid_coordinate(
                    row.get(longitude_col),
                    minimum=-180.0,
                    maximum=180.0,
                )

                date_valid = _is_valid_iso_date(
                    row.get(date_col)
                )

                if not (
                    latitude_valid
                    and longitude_valid
                    and date_valid
                ):
                    invalid_rows += 1

        except (csv.Error, UnicodeDecodeError) as exc:
            return ValidationResult(
                status="invalid",
                message=f"CSV 内容解析失败：{exc}",
                metadata={
                    "columns": fieldnames,
                },
            )

    if total_rows == 0:
        return ValidationResult(
            status="invalid",
            message="FIRMS CSV 没有数据记录。",
            metadata={
                "columns": fieldnames,
                "total_rows": 0,
            },
        )

    if invalid_rows == total_rows:
        return ValidationResult(
            status="invalid",
            message="FIRMS CSV 中没有可用的基础观测记录。",
            metadata={
                "columns": fieldnames,
                "total_rows": total_rows,
                "invalid_rows": invalid_rows,
            },
        )

    warnings: list[str] = []

    if invalid_rows > 0:
        warnings.append(
            f"发现 {invalid_rows} 行经纬度或日期无效"
        )

    if instrument_col is None:
        warnings.append(
            "缺少 instrument 字段"
        )

    if confidence_col is None:
        warnings.append(
            "缺少 confidence 字段"
        )

    metadata = {
        "columns": fieldnames,
        "total_rows": total_rows,
        "invalid_rows": invalid_rows,
        "valid_basic_rows": (
            total_rows - invalid_rows
        ),
        "latitude_column": latitude_col,
        "longitude_column": longitude_col,
        "date_column": date_col,
        "instrument_column": instrument_col,
        "confidence_column": confidence_col,
    }

    if warnings:
        return ValidationResult(
            status="valid_with_warnings",
            message="；".join(warnings),
            metadata=metadata,
        )

    return ValidationResult(
        status="valid",
        message="FIRMS CSV 基础校验通过。",
        metadata=metadata,
    )


def _parse_mcd64_name(
    path: Path,
) -> tuple[int, int] | None:
    match = MCD64_NAME_PATTERN.search(path.name)

    if match is None:
        return None

    year = int(match.group("year"))
    doy = int(match.group("doy"))

    try:
        parsed = (
            date(year, 1, 1)
            + timedelta(days=doy - 1)
        )
    except ValueError:
        return None

    if parsed.year != year:
        return None

    return year, doy


def validate_mcd64_geotiff(
    path: str | Path,
    *,
    file_role: str,
) -> ValidationResult:
    """校验 MCD64A1 GeoTIFF 的当前软件支持条件。"""

    source_path = Path(path)

    if file_role not in {
        "mcd64_burn_date",
        "mcd64_qa",
    }:
        raise ValueError(
            f"不支持的 MCD64 文件角色：{file_role}"
        )

    if source_path.suffix.lower() not in {
        ".tif",
        ".tiff",
    }:
        return ValidationResult(
            status="invalid",
            message="MCD64A1 输入文件必须为 GeoTIFF。",
            metadata={},
        )

    if not source_path.is_file():
        return ValidationResult(
            status="invalid",
            message="MCD64A1 GeoTIFF 文件不存在。",
            metadata={},
        )

    if source_path.stat().st_size == 0:
        return ValidationResult(
            status="invalid",
            message="MCD64A1 GeoTIFF 文件为空。",
            metadata={},
        )

    parsed_name = _parse_mcd64_name(
        source_path
    )

    if parsed_name is None:
        return ValidationResult(
            status="invalid",
            message=(
                "无法从文件名识别 AYYYYDDD；"
                "当前 MCD64A1 处理流程需要月度产品日期标识。"
            ),
            metadata={},
        )

    try:
        from osgeo import gdal, osr
    except ImportError:
        return ValidationResult(
            status="invalid",
            message=(
                "当前 Python 环境未检测到 GDAL，"
                "无法校验 MCD64A1 GeoTIFF。"
            ),
            metadata={
                "dependency": "GDAL",
            },
        )

    # 显式启用 GDAL Python 异常机制，
    # 避免依赖将在 GDAL 4.0 中改变的默认行为。
    gdal.UseExceptions()

    try:
        dataset = gdal.Open(
            str(source_path),
            gdal.GA_ReadOnly,
        )
    except RuntimeError as exc:
        return ValidationResult(
            status="invalid",
            message=(
                "GDAL 无法打开该 GeoTIFF："
                f"{exc}"
            ),
            metadata={},
        )

    if dataset is None:
        return ValidationResult(
            status="invalid",
            message="GDAL 无法打开该 GeoTIFF。",
            metadata={},
        )

    try:
        width = int(dataset.RasterXSize)
        height = int(dataset.RasterYSize)
        band_count = int(dataset.RasterCount)

        if (
            width <= 0
            or height <= 0
            or band_count < 1
        ):
            return ValidationResult(
                status="invalid",
                message="GeoTIFF 栅格尺寸或波段数量无效。",
                metadata={
                    "width": width,
                    "height": height,
                    "band_count": band_count,
                },
            )

        geotransform = dataset.GetGeoTransform(
            can_return_null=True
        )

        if geotransform is None:
            return ValidationResult(
                status="invalid",
                message="GeoTIFF 缺少地理变换参数。",
                metadata={
                    "width": width,
                    "height": height,
                },
            )

        (
            _x_origin,
            x_step,
            x_rotation,
            _y_origin,
            y_rotation,
            y_step,
        ) = geotransform

        if (
            abs(x_rotation) > 1e-12
            or abs(y_rotation) > 1e-12
        ):
            return ValidationResult(
                status="invalid",
                message=(
                    "当前版本只支持无旋转的"
                    "北向上 GeoTIFF。"
                ),
                metadata={
                    "geotransform": list(
                        geotransform
                    ),
                },
            )

        if x_step <= 0 or y_step >= 0:
            return ValidationResult(
                status="invalid",
                message=(
                    "GeoTIFF 像元方向不符合"
                    "当前北向上处理算法。"
                ),
                metadata={
                    "geotransform": list(
                        geotransform
                    ),
                },
            )

        projection = (
            dataset.GetProjectionRef() or ""
        )

        if not projection:
            return ValidationResult(
                status="invalid",
                message="GeoTIFF 缺少坐标参考系统。",
                metadata={},
            )

        source_srs = osr.SpatialReference()

        if source_srs.ImportFromWkt(
            projection
        ) != 0:
            return ValidationResult(
                status="invalid",
                message="无法解析 GeoTIFF 坐标参考系统。",
                metadata={},
            )

        expected_srs = osr.SpatialReference()
        expected_srs.ImportFromEPSG(4326)

        if not bool(
            source_srs.IsSame(expected_srs)
        ):
            return ValidationResult(
                status="invalid",
                message=(
                    "当前版本只支持 EPSG:4326 "
                    "GeoTIFF。"
                ),
                metadata={
                    "projection_wkt": projection,
                },
            )

        band = dataset.GetRasterBand(1)

        if band is None:
            return ValidationResult(
                status="invalid",
                message="无法读取 GeoTIFF 第一波段。",
                metadata={},
            )

        year, month_start_doy = parsed_name

        metadata = {
            "width": width,
            "height": height,
            "band_count": band_count,
            "geotransform": list(
                geotransform
            ),
            "crs": "EPSG:4326",
            "year": year,
            "month_start_doy": month_start_doy,
            "gdal_data_type": (
                gdal.GetDataTypeName(
                    band.DataType
                )
            ),
        }

        return ValidationResult(
            status="valid",
            message=(
                "MCD64A1 GeoTIFF 基础校验通过。"
            ),
            metadata=metadata,
        )

    finally:
        dataset = None


def validate_input_file(
    path: str | Path,
    *,
    file_role: str,
) -> ValidationResult:
    """按照输入文件角色执行对应基础校验。"""

    if file_role not in SUPPORTED_FILE_ROLES:
        raise ValueError(
            f"不支持的输入文件角色：{file_role}"
        )

    if file_role == "firms_csv":
        return validate_firms_csv(path)

    return validate_mcd64_geotiff(
        path,
        file_role=file_role,
    )