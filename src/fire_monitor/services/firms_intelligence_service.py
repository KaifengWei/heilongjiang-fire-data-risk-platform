# Lightweight, explainable analytics for one FIRMS analysis record.
#
# This module intentionally does not predict independent fire incidents.
# It summarizes task-scoped FIRMS active-fire observations and exposes
# interpretable temporal, radiative, regional and repeated-location signals.
#
# No network access and no new third-party dependency are required.

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


EARTH_RADIUS_KM = 6371.0088
DEFAULT_GRID_KM = 5.0
DEFAULT_REFERENCE_LAT = 48.0


@dataclass(frozen=True)
class FirmsIntelligenceResult:
    summary: dict[str, Any]
    frp: dict[str, Any]
    daynight: dict[str, Any]
    anomaly_days: list[dict[str, Any]]
    regions: list[dict[str, Any]]
    repeated_cells: list[dict[str, Any]]
    conclusions: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "frp": self.frp,
            "daynight": self.daynight,
            "anomaly_days": self.anomaly_days,
            "regions": self.regions,
            "repeated_cells": self.repeated_cells,
            "conclusions": self.conclusions,
        }


class FirmsIntelligenceService:
    COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
        "latitude": ("latitude", "lat"),
        "longitude": ("longitude", "lon", "lng"),
        "date": ("acq_date", "acquired_date", "date", "observation_date"),
        "time": ("acq_time", "time", "observation_time"),
        "frp": ("frp",),
        "confidence": ("confidence",),
        "daynight": ("daynight", "day_night"),
        "region": ("region_name", "city", "region", "region_label"),
    }

    def __init__(
        self,
        *,
        grid_km: float = DEFAULT_GRID_KM,
        reference_lat: float = DEFAULT_REFERENCE_LAT,
    ):
        if grid_km <= 0:
            raise ValueError("grid_km must be positive.")
        self.grid_km = float(grid_km)
        self.reference_lat = float(reference_lat)

    @classmethod
    def _find_column(
        cls,
        frame: pd.DataFrame,
        logical_name: str,
    ) -> str | None:
        lower_map = {str(column).lower(): str(column) for column in frame.columns}
        for alias in cls.COLUMN_ALIASES[logical_name]:
            actual = lower_map.get(alias.lower())
            if actual is not None:
                return actual
        return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(result):
            return None
        return result

    @staticmethod
    def _safe_ratio(numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return float(numerator) / float(denominator)

    @staticmethod
    def _longest_consecutive_days(values: Iterable[pd.Timestamp]) -> int:
        days = sorted({pd.Timestamp(value).date() for value in values})
        if not days:
            return 0

        longest = 1
        current = 1

        for previous, current_day in zip(days, days[1:]):
            if (current_day - previous).days == 1:
                current += 1
                longest = max(longest, current)
            else:
                current = 1

        return longest

    def _normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame(
                columns=[
                    "latitude",
                    "longitude",
                    "date",
                    "frp",
                    "confidence",
                    "daynight",
                    "region",
                ]
            )

        latitude_col = self._find_column(frame, "latitude")
        longitude_col = self._find_column(frame, "longitude")
        date_col = self._find_column(frame, "date")

        missing = [
            name
            for name, column in (
                ("latitude", latitude_col),
                ("longitude", longitude_col),
                ("acq_date/date", date_col),
            )
            if column is None
        ]

        if missing:
            raise ValueError(
                "FIRMS analysis requires columns: " + ", ".join(missing)
            )

        result = pd.DataFrame(index=frame.index.copy())

        result["latitude"] = pd.to_numeric(
            frame[latitude_col],
            errors="coerce",
        )
        result["longitude"] = pd.to_numeric(
            frame[longitude_col],
            errors="coerce",
        )
        result["date"] = pd.to_datetime(
            frame[date_col],
            errors="coerce",
        ).dt.normalize()

        frp_col = self._find_column(frame, "frp")
        result["frp"] = (
            pd.to_numeric(frame[frp_col], errors="coerce")
            if frp_col
            else np.nan
        )

        confidence_col = self._find_column(frame, "confidence")
        result["confidence"] = (
            frame[confidence_col].astype(str).str.strip()
            if confidence_col
            else ""
        )

        daynight_col = self._find_column(frame, "daynight")
        result["daynight"] = (
            frame[daynight_col]
            .astype(str)
            .str.strip()
            .str.upper()
            .str[:1]
            if daynight_col
            else ""
        )

        region_col = self._find_column(frame, "region")
        result["region"] = (
            frame[region_col]
            .where(frame[region_col].notna(), "")
            .astype(str)
            .str.strip()
            if region_col
            else ""
        )

        result = result[
            result["latitude"].between(-90, 90, inclusive="both")
            & result["longitude"].between(-180, 180, inclusive="both")
            & result["date"].notna()
        ].copy()

        return result.reset_index(drop=True)

    def _daily_statistics(
        self,
        data: pd.DataFrame,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if data.empty:
            return {
                "observation_count": 0,
                "date_start": None,
                "date_end": None,
                "span_days": 0,
                "active_days": 0,
                "activity_rate": 0.0,
                "peak_date": None,
                "peak_count": 0,
            }, []

        date_start = data["date"].min().date()
        date_end = data["date"].max().date()
        span_days = (date_end - date_start).days + 1

        daily = (
            data.groupby("date")
            .size()
            .rename("count")
            .reindex(
                pd.date_range(date_start, date_end, freq="D"),
                fill_value=0,
            )
        )

        peak_date = daily.idxmax().date()
        peak_count = int(daily.max())
        active_days = int((daily > 0).sum())

        values = daily.to_numpy(dtype=float)
        median = float(np.median(values))
        absolute_deviation = np.abs(values - median)
        mad = float(np.median(absolute_deviation))

        anomalies: list[dict[str, Any]] = []

        if mad > 0:
            robust_z = 0.6745 * (values - median) / mad

            for timestamp, count, score in zip(
                daily.index,
                daily.to_numpy(dtype=int),
                robust_z,
            ):
                if score > 3.5:
                    anomalies.append(
                        {
                            "date": timestamp.date().isoformat(),
                            "count": int(count),
                            "robust_z": round(float(score), 3),
                            "median_daily_count": round(median, 3),
                            "mad": round(mad, 3),
                        }
                    )

        anomalies.sort(
            key=lambda row: (row["robust_z"], row["count"]),
            reverse=True,
        )

        summary = {
            "observation_count": int(len(data)),
            "date_start": date_start.isoformat(),
            "date_end": date_end.isoformat(),
            "span_days": int(span_days),
            "active_days": active_days,
            "activity_rate": round(
                self._safe_ratio(active_days, span_days),
                4,
            ),
            "peak_date": peak_date.isoformat(),
            "peak_count": peak_count,
        }

        return summary, anomalies

    @staticmethod
    def _frp_statistics(data: pd.DataFrame) -> dict[str, Any]:
        values = pd.to_numeric(data["frp"], errors="coerce")
        values = values[np.isfinite(values) & (values >= 0)]

        if values.empty:
            return {
                "available_count": 0,
                "observation_sum_mw": None,
                "mean_mw": None,
                "median_mw": None,
                "p90_mw": None,
                "max_mw": None,
            }

        return {
            "available_count": int(values.size),
            "observation_sum_mw": round(float(values.sum()), 3),
            "mean_mw": round(float(values.mean()), 3),
            "median_mw": round(float(values.median()), 3),
            "p90_mw": round(float(values.quantile(0.90)), 3),
            "max_mw": round(float(values.max()), 3),
        }

    @staticmethod
    def _daynight_statistics(data: pd.DataFrame) -> dict[str, Any]:
        labels = data["daynight"].astype(str).str.upper()
        day_count = int((labels == "D").sum())
        night_count = int((labels == "N").sum())
        known = day_count + night_count

        return {
            "day_count": day_count,
            "night_count": night_count,
            "known_count": known,
            "day_share": round(day_count / known, 4) if known else None,
            "night_share": round(night_count / known, 4) if known else None,
        }

    def _regional_statistics(
        self,
        data: pd.DataFrame,
        region_areas_km2: Mapping[str, float] | None,
    ) -> list[dict[str, Any]]:
        region_data = data[data["region"].astype(str).str.len() > 0].copy()
        if region_data.empty:
            return []

        result: list[dict[str, Any]] = []
        region_areas_km2 = region_areas_km2 or {}

        for region, group in region_data.groupby("region", sort=False):
            active_days = int(group["date"].nunique())
            frp = pd.to_numeric(group["frp"], errors="coerce")
            frp = frp[np.isfinite(frp) & (frp >= 0)]

            area_value = self._safe_float(region_areas_km2.get(str(region)))
            density_per_1000 = None

            if area_value is not None and area_value > 0:
                density_per_1000 = (
                    float(len(group)) / area_value * 1000.0
                )

            result.append(
                {
                    "region_name": str(region),
                    "observation_count": int(len(group)),
                    "active_days": active_days,
                    "density_per_1000_km2": (
                        round(density_per_1000, 3)
                        if density_per_1000 is not None
                        else None
                    ),
                    "frp_mean_mw": (
                        round(float(frp.mean()), 3)
                        if not frp.empty
                        else None
                    ),
                    "frp_p90_mw": (
                        round(float(frp.quantile(0.90)), 3)
                        if not frp.empty
                        else None
                    ),
                    "frp_max_mw": (
                        round(float(frp.max()), 3)
                        if not frp.empty
                        else None
                    ),
                }
            )

        result.sort(
            key=lambda row: row["observation_count"],
            reverse=True,
        )
        return result

    def _grid_coordinates(
        self,
        latitude: pd.Series,
        longitude: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:
        lat_rad = np.radians(latitude.astype(float))
        lon_rad = np.radians(longitude.astype(float))
        reference = math.radians(self.reference_lat)

        x_km = EARTH_RADIUS_KM * lon_rad * math.cos(reference)
        y_km = EARTH_RADIUS_KM * lat_rad

        grid_x = np.floor(x_km / self.grid_km).astype("int64")
        grid_y = np.floor(y_km / self.grid_km).astype("int64")
        return grid_x, grid_y

    def _repeated_cells(
        self,
        data: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        if data.empty:
            return []

        grid = data.copy()
        grid["grid_x"], grid["grid_y"] = self._grid_coordinates(
            grid["latitude"],
            grid["longitude"],
        )

        repeated: list[dict[str, Any]] = []

        for (grid_x, grid_y), group in grid.groupby(
            ["grid_x", "grid_y"],
            sort=False,
        ):
            active_days = int(group["date"].nunique())
            if active_days < 2:
                continue

            frp = pd.to_numeric(group["frp"], errors="coerce")
            frp = frp[np.isfinite(frp) & (frp >= 0)]

            regions = (
                group["region"]
                .loc[group["region"].astype(str).str.len() > 0]
                .value_counts()
            )
            dominant_region = (
                str(regions.index[0])
                if not regions.empty
                else None
            )

            active_dates = sorted(
                {
                    value.date().isoformat()
                    for value in group["date"]
                }
            )

            repeated.append(
                {
                    "grid_id": f"{int(grid_x)}:{int(grid_y)}",
                    "grid_km": self.grid_km,
                    "center_latitude": round(
                        float(group["latitude"].mean()),
                        5,
                    ),
                    "center_longitude": round(
                        float(group["longitude"].mean()),
                        5,
                    ),
                    "region_name": dominant_region,
                    "observation_count": int(len(group)),
                    "active_days": active_days,
                    "active_dates": active_dates,
                    "longest_consecutive_days": self._longest_consecutive_days(
                        group["date"]
                    ),
                    "first_date": group["date"].min().date().isoformat(),
                    "last_date": group["date"].max().date().isoformat(),
                    "frp_mean_mw": (
                        round(float(frp.mean()), 3)
                        if not frp.empty
                        else None
                    ),
                    "frp_max_mw": (
                        round(float(frp.max()), 3)
                        if not frp.empty
                        else None
                    ),
                }
            )

        repeated.sort(
            key=lambda row: (
                row["active_days"],
                row["longest_consecutive_days"],
                row["observation_count"],
            ),
            reverse=True,
        )
        return repeated

    @staticmethod
    def _build_conclusions(
        *,
        summary: Mapping[str, Any],
        frp: Mapping[str, Any],
        daynight: Mapping[str, Any],
        anomaly_days: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        repeated_cells: list[dict[str, Any]],
    ) -> list[str]:
        conclusions: list[str] = []

        observation_count = int(summary.get("observation_count") or 0)
        if observation_count <= 0:
            return ["本次数据没有形成可用于分析的有效 FIRMS 主动火点观测。"]

        conclusions.append(
            f"本次共纳入 {observation_count:,} 条有效 FIRMS 主动火点观测，"
            f"覆盖 {summary['active_days']} 个活跃日期。"
        )

        if regions:
            top = regions[0]
            conclusions.append(
                f"{top['region_name']} 的火点观测数量最高，"
                f"共 {top['observation_count']:,} 条。"
            )

        if summary.get("peak_date"):
            conclusions.append(
                f"{summary['peak_date']} 为本次火点观测最多的日期，"
                f"当日共 {int(summary['peak_count']):,} 条。"
            )

        if anomaly_days:
            top_anomaly = anomaly_days[0]
            conclusions.append(
                f"{top_anomaly['date']} 达到鲁棒异常高值判定，"
                f"当天火点观测明显高于本次时间序列的常见水平。"
            )

        if repeated_cells:
            top_cell = repeated_cells[0]
            region_text = (
                f"{top_cell['region_name']}附近"
                if top_cell.get("region_name")
                else "一个局部区域"
            )
            conclusions.append(
                f"检测到 {len(repeated_cells)} 个在至少两个日期重复出现火点的 "
                f"{DEFAULT_GRID_KM:g} km 网格；其中 {region_text} 的重复活动最突出，"
                f"共出现 {top_cell['active_days']} 个活跃日期。"
            )

        if daynight.get("known_count"):
            day_share = daynight.get("day_share")
            night_share = daynight.get("night_share")

            if day_share is not None and night_share is not None:
                if day_share >= 0.65:
                    conclusions.append(
                        f"有昼夜标识的观测中，白天观测约占 {day_share:.0%}。"
                    )
                elif night_share >= 0.65:
                    conclusions.append(
                        f"有昼夜标识的观测中，夜间观测约占 {night_share:.0%}。"
                    )

        if frp.get("available_count"):
            conclusions.append(
                f"本次有 {int(frp['available_count']):,} 条观测包含 FRP，"
                f"其中 90% 分位 FRP 为 {frp['p90_mw']:.1f} MW，"
                f"最大值为 {frp['max_mw']:.1f} MW。"
            )

        return conclusions

    def analyze(
        self,
        frame: pd.DataFrame | list[dict[str, Any]],
        *,
        region_areas_km2: Mapping[str, float] | None = None,
    ) -> FirmsIntelligenceResult:
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(frame)

        data = self._normalize(frame)

        summary, anomaly_days = self._daily_statistics(data)
        frp = self._frp_statistics(data)
        daynight = self._daynight_statistics(data)
        regions = self._regional_statistics(
            data,
            region_areas_km2,
        )
        repeated_cells = self._repeated_cells(data)

        conclusions = self._build_conclusions(
            summary=summary,
            frp=frp,
            daynight=daynight,
            anomaly_days=anomaly_days,
            regions=regions,
            repeated_cells=repeated_cells,
        )

        return FirmsIntelligenceResult(
            summary=summary,
            frp=frp,
            daynight=daynight,
            anomaly_days=anomaly_days,
            regions=regions,
            repeated_cells=repeated_cells,
            conclusions=conclusions,
        )
