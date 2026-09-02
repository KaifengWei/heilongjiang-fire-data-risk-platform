"""FIRMS 主动火点数据规范化与可选在线下载。
本模块处理的是“主动火点观测记录”，不是独立火灾事件。

核心原则：
1. 对日期、时间、坐标和传感器字段进行规范化；
2. 明确记录被拒绝的原因；
3. 区分观测本身的身份与数据来源身份；
4. NRT / SP 等不同处理来源不应仅因为来源名称不同，就被统计为两条完全独立的相同观测；
5. 不对不同时间、不同卫星或不同像元执行模糊火灾事件合并。
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from typing import Any, Iterator

import pandas as pd
import requests


FIRMS_AREA_API = (
    "https://firms.modaps.eosdis.nasa.gov/"
    "api/area/csv"
)

QUALITY_RULE_NAME = (
    "VIIRS:n/h; MODIS:confidence>=30"
)


@dataclass(frozen=True)
class FirmsNormalizationResult:
    """一次 FIRMS 表格规范化处理结果。"""

    rows: list[dict[str, Any]]
    input_rows: int
    accepted_rows: int
    rejected_rows: int
    rejection_counts: dict[str, int]


def _column_lookup(
    frame: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    normalized = {
        str(column)
        .strip()
        .lower()
        .lstrip("\ufeff"): column
        for column in frame.columns
    }

    for candidate in candidates:
        match = normalized.get(
            candidate.lower()
        )

        if match is not None:
            return match

    return None


def _as_text(
    value: Any,
) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()

    return text or None


def _as_float(
    value: Any,
) -> float | None:
    parsed = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]

    if pd.isna(parsed):
        return None

    return float(parsed)


def normalize_acq_time(
    value: Any,
) -> str | None:
    """将 FIRMS acquisition time 规范化为四位 HHMM。

    示例：
    3       -> "0003"
    35      -> "0035"
    930     -> "0930"
    "1425"  -> "1425"

    无法构成有效 UTC HHMM 时返回 None。
    """

    text = _as_text(value)

    if text is None:
        return None

    # Pandas 读取纯数字列时可能得到 3.0。
    if re.fullmatch(
        r"\d+\.0+",
        text,
    ):
        text = text.split(
            ".",
            maxsplit=1,
        )[0]

    if not text.isdigit():
        return None

    if len(text) > 4:
        return None

    text = text.zfill(4)

    hour = int(text[:2])
    minute = int(text[2:])

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return None

    return text


def firms_quality_pass(
    instrument: str | None,
    confidence: Any,
) -> bool:
    """执行项目当前明确采用的 FIRMS 质量规则。

    VIIRS：
        保留 nominal (n) 与 high (h)。

    MODIS：
        保留 confidence >= 30。

    这是本平台采用的数据筛选策略，
    不表述为 NASA 强制要求的唯一阈值。
    """

    instrument_text = (
        instrument or ""
    ).strip().upper()

    confidence_text = _as_text(
        confidence
    )

    if instrument_text == "VIIRS":
        return (
            confidence_text or ""
        ).lower() in {
            "n",
            "h",
        }

    if instrument_text == "MODIS":
        value = _as_float(
            confidence
        )

        return (
            value is not None
            and value >= 30
        )

    return False


def infer_processing_class(
    *,
    firms_source: str | None,
    version: str | None,
) -> str:
    """识别 FIRMS 数据处理阶段。

    返回：
    URT / RT / NRT / SP / UNKNOWN

    优先使用显式来源名称；
    若来源名称没有信息，再检查 CSV version 字段。
    """

    source_text = (
        firms_source or ""
    ).strip().upper()

    version_text = (
        version or ""
    ).strip().upper()

    combined = (
        f"{source_text} {version_text}"
    )

    if "URT" in combined:
        return "URT"

    if "NRT" in combined:
        return "NRT"

    if re.search(
        r"(^|[^A-Z])RT($|[^A-Z])",
        combined,
    ):
        return "RT"

    if (
        source_text.endswith("_SP")
        or source_text == "SP"
    ):
        return "SP"

    # FIRMS 的标准处理 version 通常只有
    # collection/version 本身，不带 NRT/RT/URT 后缀。
    if (
        version_text
        and re.fullmatch(
            r"\d+(?:\.\d+)?",
            version_text,
        )
    ):
        return "SP"

    return "UNKNOWN"


def canonical_observation_key(
    *,
    acquired_date: str,
    acquired_time: str | None,
    latitude: float,
    longitude: float,
    instrument: str | None,
    satellite: str | None,
) -> str:
    """生成主动火点观测的规范身份键。

    刻意不包含：
    - firms_source
    - processing_class
    - version

    因为这些描述的是数据处理来源，
    不是卫星观测本身。

    本键只用于“精确观测去重”，
    不用于把邻近像元或多次过境合并成火灾事件。
    """

    parts = [
        acquired_date,
        acquired_time or "",
        f"{latitude:.6f}",
        f"{longitude:.6f}",
        (
            instrument or ""
        ).strip().upper(),
        (
            satellite or ""
        ).strip().upper(),
    ]

    return hashlib.sha256(
        "|".join(parts).encode(
            "utf-8"
        )
    ).hexdigest()


def source_record_key(
    *,
    canonical_key: str,
    firms_source: str,
    processing_class: str,
    version: str | None,
) -> str:
    """生成来源记录身份键。

    与 canonical_observation_key 不同，
    本键用于区分同一观测来自哪个处理版本。
    """

    parts = [
        canonical_key,
        firms_source.strip(),
        processing_class,
        version or "",
    ]

    return hashlib.sha256(
        "|".join(parts).encode(
            "utf-8"
        )
    ).hexdigest()


def normalize_firms_dataframe(
    frame: pd.DataFrame,
    *,
    firms_source: str,
    quality_only: bool = True,
    region_column: str | None = None,
    strict_identity: bool = True,
) -> FirmsNormalizationResult:
    """正式规范化 FIRMS DataFrame。

    strict_identity=True 时，
    为建立可靠观测身份，要求 CSV 具备：

    latitude
    longitude
    acq_date
    acq_time
    instrument
    satellite
    confidence

    version 为推荐字段，但不是强制字段。
    """

    latitude_col = _column_lookup(
        frame,
        ["latitude", "lat"],
    )

    longitude_col = _column_lookup(
        frame,
        ["longitude", "lon", "lng"],
    )

    date_col = _column_lookup(
        frame,
        [
            "acq_date",
            "date",
            "日期",
        ],
    )

    time_col = _column_lookup(
        frame,
        [
            "acq_time",
            "time",
            "时间",
        ],
    )

    instrument_col = _column_lookup(
        frame,
        [
            "instrument",
            "传感器",
        ],
    )

    satellite_col = _column_lookup(
        frame,
        [
            "satellite",
            "卫星",
        ],
    )

    confidence_col = _column_lookup(
        frame,
        [
            "confidence",
            "置信度",
        ],
    )

    version_col = _column_lookup(
        frame,
        ["version"],
    )

    frp_col = _column_lookup(
        frame,
        ["frp"],
    )

    scan_col = _column_lookup(
        frame,
        ["scan"],
    )

    track_col = _column_lookup(
        frame,
        ["track"],
    )

    required = {
        "latitude": latitude_col,
        "longitude": longitude_col,
        "acq_date": date_col,
    }

    if strict_identity:
        required.update(
            {
                "acq_time": time_col,
                "instrument": (
                    instrument_col
                ),
                "satellite": (
                    satellite_col
                ),
                "confidence": (
                    confidence_col
                ),
            }
        )

    missing = [
        name
        for name, column
        in required.items()
        if column is None
    ]

    if missing:
        raise ValueError(
            "FIRMS CSV 缺少正式处理所需字段："
            + ", ".join(missing)
        )

    rows: list[
        dict[str, Any]
    ] = []

    rejection_counts: Counter[str] = (
        Counter()
    )

    for raw in frame.to_dict(
        orient="records"
    ):
        latitude = _as_float(
            raw.get(latitude_col)
        )

        if (
            latitude is None
            or not -90.0
            <= latitude
            <= 90.0
        ):
            rejection_counts[
                "invalid_latitude"
            ] += 1
            continue

        longitude = _as_float(
            raw.get(longitude_col)
        )

        if (
            longitude is None
            or not -180.0
            <= longitude
            <= 180.0
        ):
            rejection_counts[
                "invalid_longitude"
            ] += 1
            continue

        parsed_date = pd.to_datetime(
            raw.get(date_col),
            errors="coerce",
        )

        if pd.isna(parsed_date):
            rejection_counts[
                "invalid_date"
            ] += 1
            continue

        acquired_date = (
            parsed_date
            .date()
            .isoformat()
        )

        acquired_time = (
            normalize_acq_time(
                raw.get(time_col)
            )
            if time_col
            else None
        )

        if (
            strict_identity
            and acquired_time is None
        ):
            rejection_counts[
                "invalid_time"
            ] += 1
            continue

        instrument = (
            _as_text(
                raw.get(
                    instrument_col
                )
            )
            if instrument_col
            else None
        )

        if instrument:
            instrument = (
                instrument.upper()
            )

        if (
            strict_identity
            and not instrument
        ):
            rejection_counts[
                "missing_instrument"
            ] += 1
            continue

        satellite = (
            _as_text(
                raw.get(
                    satellite_col
                )
            )
            if satellite_col
            else None
        )

        if satellite:
            satellite = (
                satellite.upper()
            )

        if (
            strict_identity
            and not satellite
        ):
            rejection_counts[
                "missing_satellite"
            ] += 1
            continue

        confidence = (
            _as_text(
                raw.get(
                    confidence_col
                )
            )
            if confidence_col
            else None
        )

        if (
            strict_identity
            and confidence is None
        ):
            rejection_counts[
                "missing_confidence"
            ] += 1
            continue

        accepted_quality = (
            firms_quality_pass(
                instrument,
                confidence,
            )
        )

        if (
            quality_only
            and not accepted_quality
        ):
            rejection_counts[
                "quality_rejected"
            ] += 1
            continue

        version = (
            _as_text(
                raw.get(version_col)
            )
            if version_col
            else None
        )

        processing_class = (
            infer_processing_class(
                firms_source=(
                    firms_source
                ),
                version=version,
            )
        )

        canonical_key = (
            canonical_observation_key(
                acquired_date=(
                    acquired_date
                ),
                acquired_time=(
                    acquired_time
                ),
                latitude=latitude,
                longitude=longitude,
                instrument=instrument,
                satellite=satellite,
            )
        )

        record_key = (
            source_record_key(
                canonical_key=(
                    canonical_key
                ),
                firms_source=(
                    firms_source
                ),
                processing_class=(
                    processing_class
                ),
                version=version,
            )
        )

        rows.append(
            {
                # 保留 dedupe_key 名称，
                # 兼容当前数据库写入接口。
                "dedupe_key": (
                    canonical_key
                ),
                "canonical_key": (
                    canonical_key
                ),
                "source_record_key": (
                    record_key
                ),
                "acquired_date": (
                    acquired_date
                ),
                "acquired_time": (
                    acquired_time
                ),
                "latitude": latitude,
                "longitude": longitude,
                "firms_source": (
                    firms_source
                ),
                "processing_class": (
                    processing_class
                ),
                "source_version": (
                    version
                ),
                "instrument": instrument,
                "satellite": satellite,
                "confidence": confidence,
                "frp": (
                    _as_float(
                        raw.get(frp_col)
                    )
                    if frp_col
                    else None
                ),
                "scan": (
                    _as_float(
                        raw.get(scan_col)
                    )
                    if scan_col
                    else None
                ),
                "track": (
                    _as_float(
                        raw.get(track_col)
                    )
                    if track_col
                    else None
                ),
                "quality_rule": (
                    QUALITY_RULE_NAME
                    if quality_only
                    else (
                        "未执行质量筛选"
                    )
                ),
                "source_region_name": (
                    _as_text(
                        raw.get(
                            region_column
                        )
                    )
                    if region_column
                    else None
                ),
            }
        )

    input_rows = len(frame)

    accepted_rows = len(rows)

    rejected_rows = (
        input_rows
        - accepted_rows
    )

    return FirmsNormalizationResult(
        rows=rows,
        input_rows=input_rows,
        accepted_rows=(
            accepted_rows
        ),
        rejected_rows=(
            rejected_rows
        ),
        rejection_counts=dict(
            rejection_counts
        ),
    )


def normalized_firms_rows(
    frame: pd.DataFrame,
    *,
    firms_source: str,
    quality_only: bool,
    region_column: str | None = None,
) -> Iterator[
    dict[str, Any]
]:
    """兼容原有 ImportService 的迭代接口。

    这里保持旧接口允许缺少 acq_time / satellite，
    Day 4 后续正式任务处理将切换到
    normalize_firms_dataframe(strict_identity=True)。
    """

    result = (
        normalize_firms_dataframe(
            frame,
            firms_source=(
                firms_source
            ),
            quality_only=(
                quality_only
            ),
            region_column=(
                region_column
            ),
            strict_identity=False,
        )
    )

    yield from result.rows


def split_firms_date_ranges(
    start: date,
    end: date,
    max_days: int = 5,
) -> Iterator[
    tuple[date, int]
]:
    """将 FIRMS API 日期范围拆成小批次。"""

    current = start

    while current <= end:
        days = min(
            max_days,
            (
                end - current
            ).days + 1,
        )

        yield (
            current,
            days,
        )

        current += timedelta(
            days=days
        )


def fetch_firms_area_csv(
    *,
    source: str,
    bbox: str,
    start: date,
    end: date,
    map_key: str | None = None,
    timeout_seconds: int = 60,
) -> pd.DataFrame:
    """调用 FIRMS Area API。

    MAP_KEY 默认只从环境变量 FIRMS_MAP_KEY 读取。
    """

    key = (
        map_key
        or os.environ.get(
            "FIRMS_MAP_KEY"
        )
    )

    if not key:
        raise RuntimeError(
            "未找到 FIRMS_MAP_KEY。"
            "请先在本机环境变量中设置 MAP_KEY。"
        )

    pieces: list[
        pd.DataFrame
    ] = []

    for (
        block_start,
        days,
    ) in split_firms_date_ranges(
        start,
        end,
    ):
        url = (
            f"{FIRMS_AREA_API}/"
            f"{key}/"
            f"{source}/"
            f"{bbox}/"
            f"{days}/"
            f"{block_start.isoformat()}"
        )

        response = requests.get(
            url,
            timeout=(
                timeout_seconds
            ),
        )

        response.raise_for_status()

        text = (
            response.text.strip()
        )

        if (
            text
            and not text
            .lower()
            .startswith("no data")
        ):
            pieces.append(
                pd.read_csv(
                    StringIO(text)
                )
            )

    if not pieces:
        return pd.DataFrame()

    return pd.concat(
        pieces,
        ignore_index=True,
    )