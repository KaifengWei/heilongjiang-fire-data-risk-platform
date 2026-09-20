"""历史 FIRMS 同期基线构建与任务级比较。"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from fire_monitor.core.firms import normalize_firms_dataframe
from fire_monitor.core.geography import RegionIndex, load_regions_from_geojson
from fire_monitor.services.import_service import read_csv_with_fallback


BASELINE_SCHEMA_VERSION = 1
DEFAULT_PRODUCT_ID = "VIIRS_NOAA20_375M"
DEFAULT_MIN_REFERENCE_YEARS = 4

NOAA20_ALIASES = {
    "N20",
    "NOAA-20",
    "NOAA20",
    "1",
    "J1",
    "JPSS-1",
}


def _canonical_satellite(value: Any) -> str:
    return str(value or "").strip().upper().replace("_", "-")


def _is_noaa20(value: Any) -> bool:
    return _canonical_satellite(value) in NOAA20_ALIASES


def _safe_date(value: Any) -> date | None:
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def _historical_status(values: list[int], current: int) -> tuple[str, str]:
    if not values:
        return "暂无历史参照", "没有可用于比较的历史年份。"

    ordered = sorted(int(value) for value in values)
    median = float(np.median(ordered))
    rank = sum(value <= current for value in ordered) / len(ordered)

    if current > max(ordered):
        return (
            "明显高于历史同期",
            f"当前数量高于全部 {len(ordered)} 个可比历史年份。",
        )

    if current < min(ordered):
        return (
            "明显低于历史同期",
            f"当前数量低于全部 {len(ordered)} 个可比历史年份。",
        )

    if current > median and rank >= 0.75:
        return "高于历史同期", "当前数量高于多数可比历史年份。"

    if current < median and rank <= 0.25:
        return "低于历史同期", "当前数量低于多数可比历史年份。"

    return "接近历史同期", "当前数量位于历史同期常见范围内。"


class HistoricalFirmsBaselineBuilder:
    """把开发者下载的真实 FIRMS Archive CSV 压缩为日级基线。"""

    def __init__(
        self,
        *,
        region_geojson_path: str | Path,
        expected_years: Iterable[int],
    ):
        self.region_geojson_path = Path(region_geojson_path)
        self.expected_years = sorted({int(year) for year in expected_years})

        if not self.expected_years:
            raise ValueError("expected_years 不能为空。")

    def _region_index(self) -> RegionIndex:
        regions = load_regions_from_geojson(
            self.region_geojson_path,
            name_field="name",
            level="city",
        )
        return RegionIndex(regions)

    def build(
        self,
        csv_paths: Iterable[str | Path],
        *,
        output_path: str | Path,
    ) -> dict[str, Any]:
        paths = [Path(path) for path in csv_paths]

        if not paths:
            raise ValueError("至少需要一个 FIRMS Archive CSV。")

        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(path)

        region_index = self._region_index()
        expected_years = set(self.expected_years)

        daily: dict[str, dict[str, Any]] = {}
        seen_canonical_keys: set[str] = set()

        report = Counter()
        observed_years: set[int] = set()
        processing_classes = Counter()

        for path in sorted(paths):
            frame = read_csv_with_fallback(path, low_memory=False)
            report["input_rows"] += int(len(frame))

            normalized = normalize_firms_dataframe(
                frame,
                firms_source="NASA_FIRMS_ARCHIVE",
                quality_only=True,
                strict_identity=True,
            )

            report["normalized_rows"] += normalized.accepted_rows
            report["quality_rejected"] += int(
                normalized.rejection_counts.get("quality_rejected", 0)
            )

            for row in normalized.rows:
                if str(row.get("instrument") or "").upper() != "VIIRS":
                    report["non_viirs_rows"] += 1
                    continue

                if not _is_noaa20(row.get("satellite")):
                    report["non_noaa20_rows"] += 1
                    continue

                acquired = _safe_date(row.get("acquired_date"))
                if acquired is None:
                    report["invalid_dates"] += 1
                    continue

                if acquired.year not in expected_years:
                    report["outside_expected_years"] += 1
                    continue

                processing_class = str(
                    row.get("processing_class") or "UNKNOWN"
                ).upper()
                processing_classes[processing_class] += 1

                if processing_class != "SP":
                    report["non_science_quality_rows"] += 1
                    continue

                canonical_key = str(row["canonical_key"])

                if canonical_key in seen_canonical_keys:
                    report["duplicate_observations"] += 1
                    continue

                seen_canonical_keys.add(canonical_key)

                region_name = region_index.locate(
                    float(row["longitude"]),
                    float(row["latitude"]),
                )

                if not region_name:
                    report["outside_regions"] += 1
                    continue

                date_key = acquired.isoformat()
                item = daily.setdefault(
                    date_key,
                    {"total": 0, "regions": {}},
                )
                item["total"] = int(item["total"]) + 1
                item["regions"][region_name] = (
                    int(item["regions"].get(region_name, 0)) + 1
                )

                observed_years.add(acquired.year)
                report["accepted_baseline_observations"] += 1

        missing_years = sorted(expected_years - observed_years)
        if missing_years:
            raise ValueError(
                "基线缺少预期年份的有效 NOAA-20 标准处理观测："
                + ", ".join(str(year) for year in missing_years)
            )

        payload = {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "product_id": DEFAULT_PRODUCT_ID,
            "source": "NASA FIRMS Archive",
            "quality_policy": (
                "VIIRS confidence n/h; standard processing only"
            ),
            "expected_years": self.expected_years,
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "report": {
                key: int(value)
                for key, value in sorted(report.items())
            },
            "processing_class_counts": dict(
                sorted(processing_classes.items())
            ),
            "daily": {
                key: daily[key]
                for key in sorted(daily)
            },
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        return payload


class HistoricalFirmsBaselineService:
    """把当前任务与 NOAA-20 历史同期进行解释性比较。"""

    def __init__(
        self,
        baseline_path: str | Path,
        *,
        min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
    ):
        self.baseline_path = Path(baseline_path)
        self.min_reference_years = int(min_reference_years)
        self._payload: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any] | None:
        if self._payload is not None:
            return self._payload

        if not self.baseline_path.is_file():
            return None

        payload = json.loads(
            self.baseline_path.read_text(encoding="utf-8")
        )

        if int(payload.get("schema_version", -1)) != BASELINE_SCHEMA_VERSION:
            raise ValueError("历史 FIRMS 基线版本不受支持。")

        if payload.get("product_id") != DEFAULT_PRODUCT_ID:
            raise ValueError("历史 FIRMS 基线产品与当前服务不匹配。")

        self._payload = payload
        return payload

    @staticmethod
    def _period_dates(start: date, end: date) -> list[date]:
        if end < start:
            return []

        return [
            item.date()
            for item in pd.date_range(start, end, freq="D")
        ]

    @staticmethod
    def _map_period(
        current_dates: list[date],
        reference_year: int,
    ) -> list[date] | None:
        if not current_dates:
            return None

        base_year = current_dates[0].year
        result: list[date] = []

        for current in current_dates:
            year_offset = current.year - base_year
            target_year = reference_year + year_offset

            try:
                result.append(
                    date(target_year, current.month, current.day)
                )
            except ValueError:
                return None

        return result

    @staticmethod
    def _current_frame(
        rows: list[dict[str, Any]],
    ) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(
                columns=["date", "region", "satellite"]
            )

        frame = pd.DataFrame(rows)

        date_col = (
            "acquired_date"
            if "acquired_date" in frame.columns
            else "acq_date"
        )
        region_col = (
            "region_name"
            if "region_name" in frame.columns
            else "region"
        )

        result = pd.DataFrame()
        result["date"] = pd.to_datetime(
            frame.get(date_col),
            errors="coerce",
        ).dt.date
        result["region"] = (
            frame.get(region_col, pd.Series("", index=frame.index))
            .fillna("")
            .astype(str)
            .str.strip()
        )
        result["satellite"] = (
            frame.get("satellite", pd.Series("", index=frame.index))
            .fillna("")
            .astype(str)
            .str.strip()
        )

        return result[result["date"].notna()].copy()

    def compare(
        self,
        rows: list[dict[str, Any]],
        *,
        analysis_start: str | None = None,
        analysis_end: str | None = None,
    ) -> dict[str, Any]:
        payload = self._load()

        if payload is None:
            return {
                "available": False,
                "reason": "baseline_not_installed",
            }

        current = self._current_frame(rows)

        if current.empty:
            return {
                "available": False,
                "reason": "no_current_observations",
            }

        satellites = {
            value
            for value in current["satellite"]
            if value
        }

        if satellites and not all(_is_noaa20(value) for value in satellites):
            return {
                "available": False,
                "reason": "current_product_not_noaa20",
            }

        start = (
            _safe_date(analysis_start)
            if analysis_start
            else min(current["date"])
        )
        end = (
            _safe_date(analysis_end)
            if analysis_end
            else max(current["date"])
        )

        if start is None or end is None or end < start:
            return {
                "available": False,
                "reason": "invalid_current_period",
            }

        current_dates = self._period_dates(start, end)
        current_year = start.year

        baseline_years = [
            int(year)
            for year in payload.get("expected_years", [])
            if int(year) < current_year
        ]

        daily = payload.get("daily") or {}

        comparison_years: list[int] = []
        province_history: list[int] = []
        region_history_by_year: list[Counter[str]] = []

        for reference_year in baseline_years:
            mapped_dates = self._map_period(
                current_dates,
                reference_year,
            )

            if mapped_dates is None:
                continue

            total = 0
            region_counts: Counter[str] = Counter()

            for mapped in mapped_dates:
                item = daily.get(mapped.isoformat()) or {}
                total += int(item.get("total", 0) or 0)

                for region_name, count in (
                    item.get("regions") or {}
                ).items():
                    region_counts[str(region_name)] += int(count or 0)

            comparison_years.append(reference_year)
            province_history.append(int(total))
            region_history_by_year.append(region_counts)

        if len(comparison_years) < self.min_reference_years:
            return {
                "available": False,
                "reason": "insufficient_reference_years",
                "reference_years": comparison_years,
            }

        current_total = int(len(current))
        province_status, province_reason = _historical_status(
            province_history,
            current_total,
        )

        current_region_counts = Counter(
            value
            for value in current["region"]
            if value
        )

        all_regions = sorted(
            set(current_region_counts).union(
                *(
                    set(counter)
                    for counter in region_history_by_year
                )
            )
        )

        positive_counts = sorted(
            (
                int(current_region_counts.get(region, 0))
                for region in all_regions
                if int(current_region_counts.get(region, 0)) > 0
            ),
            reverse=True,
        )

        top_quartile_cutoff = 0
        if positive_counts:
            top_count = max(
                1,
                math.ceil(len(positive_counts) * 0.25),
            )
            top_quartile_cutoff = positive_counts[top_count - 1]

        regions: list[dict[str, Any]] = []

        for region_name in all_regions:
            historical = [
                int(counter.get(region_name, 0))
                for counter in region_history_by_year
            ]

            current_count = int(
                current_region_counts.get(region_name, 0)
            )

            status, reason = _historical_status(
                historical,
                current_count,
            )

            concentrated = (
                current_count > 0
                and top_quartile_cutoff > 0
                and current_count >= top_quartile_cutoff
            )

            if status == "明显高于历史同期" and concentrated:
                attention = "优先核查"
            elif status in {
                "明显高于历史同期",
                "高于历史同期",
            } or concentrated:
                attention = "建议关注"
            else:
                attention = "常规查看"

            reasons = [reason]

            if concentrated:
                reasons.append(
                    "同时属于本次火点观测较集中的地区。"
                )

            regions.append(
                {
                    "region_name": region_name,
                    "current_count": current_count,
                    "historical_status": status,
                    "attention": attention,
                    "reasons": reasons,
                    "reference_values": historical,
                }
            )

        attention_order = {
            "优先核查": 0,
            "建议关注": 1,
            "常规查看": 2,
        }

        status_order = {
            "明显高于历史同期": 0,
            "高于历史同期": 1,
            "接近历史同期": 2,
            "低于历史同期": 3,
            "明显低于历史同期": 4,
            "暂无历史参照": 5,
        }

        regions.sort(
            key=lambda item: (
                attention_order.get(item["attention"], 9),
                status_order.get(item["historical_status"], 9),
                -int(item["current_count"]),
            )
        )

        priority_regions = [
            item
            for item in regions
            if item["attention"] in {
                "优先核查",
                "建议关注",
            }
            and item["current_count"] > 0
        ][:3]

        if priority_regions:
            names = "、".join(
                item["region_name"]
                for item in priority_regions
            )
            guidance = (
                f"本次活动{province_status}，"
                f"建议先查看 {names}。"
            )
        else:
            guidance = (
                f"本次活动{province_status}，"
                "当前没有需要单独提前查看的地区。"
            )

        return {
            "available": True,
            "product_id": DEFAULT_PRODUCT_ID,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "current_count": current_total,
            "reference_years": comparison_years,
            "reference_year_count": len(comparison_years),
            "province_status": province_status,
            "province_reason": province_reason,
            "guidance": guidance,
            "priority_regions": priority_regions,
            "regions": regions,
        }
