"""Historical weather context backed by NASA POWER Daily data.

This service is for past FIRMS tasks. It does not forecast the past. Instead it
retrieves daily temperature, relative humidity, 10 m wind speed and corrected
precipitation for representative points in the most active counties, caches the
official responses locally, and summarizes the weather background around the
task period and peak fire-observation day.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import requests


POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMETERS = "T2M,RH2M,WS10M,PRECTOTCORR"
MIN_POWER_DATE = date(1981, 1, 1)


class HistoricalWeatherContextService:
    def __init__(
        self,
        cache_dir: str | Path,
        *,
        request_timeout: int = 90,
        top_counties: int = 3,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_timeout = int(request_timeout)
        self.top_counties = int(top_counties)

    @staticmethod
    def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "available": False,
            "mode": "historical",
            "reason": reason,
            **extra,
        }

    @staticmethod
    def _date_from_row(row: dict[str, Any]) -> date | None:
        raw = str(row.get("acquired_date") or "")[:10]
        if not raw:
            return None

        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    @classmethod
    def _task_dates(
        cls,
        rows: list[dict[str, Any]],
    ) -> list[date]:
        values = [
            value
            for row in rows
            if (value := cls._date_from_row(row)) is not None
        ]
        return sorted(set(values))

    @staticmethod
    def _median(values: list[float]) -> float:
        return float(np.median(np.asarray(values, dtype=float)))

    @staticmethod
    def _mean(values: list[float]) -> float:
        return float(np.mean(np.asarray(values, dtype=float)))

    @staticmethod
    def _round(value: float | None, digits: int = 1) -> float | None:
        if value is None:
            return None
        return round(float(value), digits)

    @staticmethod
    def _compact_day(value: date) -> str:
        return value.strftime("%Y%m%d")

    @staticmethod
    def _display_day(value: date) -> str:
        return value.strftime("%Y-%m-%d")

    @staticmethod
    def _task_cache_name(
        task_id: str,
        start: date,
        end: date,
    ) -> str:
        safe = "".join(
            char
            for char in str(task_id)
            if char.isalnum() or char in {"-", "_"}
        )
        return f"{safe}_{start.isoformat()}_{end.isoformat()}.json"

    def _task_cache_path(
        self,
        task_id: str,
        start: date,
        end: date,
    ) -> Path:
        path = self.cache_dir / "tasks"
        path.mkdir(parents=True, exist_ok=True)
        return path / self._task_cache_name(task_id, start, end)

    def _point_cache_path(
        self,
        *,
        latitude: float,
        longitude: float,
        start: date,
        end: date,
    ) -> Path:
        key = (
            f"{latitude:.4f}|{longitude:.4f}|"
            f"{start.isoformat()}|{end.isoformat()}|"
            f"{POWER_PARAMETERS}"
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]

        path = self.cache_dir / "points"
        path.mkdir(parents=True, exist_ok=True)

        return path / (
            f"power_{start.strftime('%Y%m%d')}_"
            f"{end.strftime('%Y%m%d')}_{digest}.json"
        )

    def _fetch_power(
        self,
        *,
        latitude: float,
        longitude: float,
        start: date,
        end: date,
    ) -> dict[str, Any] | None:
        cache = self._point_cache_path(
            latitude=latitude,
            longitude=longitude,
            start=start,
            end=end,
        )

        if cache.is_file():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        try:
            response = requests.get(
                POWER_URL,
                params={
                    "parameters": POWER_PARAMETERS,
                    "community": "AG",
                    "longitude": f"{longitude:.4f}",
                    "latitude": f"{latitude:.4f}",
                    "start": self._compact_day(start),
                    "end": self._compact_day(end),
                    "format": "JSON",
                    "time-standard": "UTC",
                },
                timeout=self.request_timeout,
                headers={
                    "User-Agent": (
                        "heilongjiang-fire-monitor/"
                        "historical-weather-context"
                    )
                },
            )
        except requests.RequestException:
            return None

        if response.status_code != 200:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        try:
            cache.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

        return payload

    @staticmethod
    def _series(
        payload: dict[str, Any],
    ) -> dict[str, dict[str, float]]:
        parameter = (
            payload.get("properties", {})
            .get("parameter", {})
        )

        if not isinstance(parameter, dict):
            return {}

        result: dict[str, dict[str, float]] = {}

        for name, values in parameter.items():
            if not isinstance(values, dict):
                continue

            cleaned: dict[str, float] = {}

            for day, value in values.items():
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue

                if numeric <= -900 or not np.isfinite(numeric):
                    continue

                cleaned[str(day)] = numeric

            result[str(name)] = cleaned

        return result

    @staticmethod
    def _daily_value(
        series: dict[str, dict[str, float]],
        parameter: str,
        day: date,
    ) -> float | None:
        value = series.get(parameter, {}).get(day.strftime("%Y%m%d"))
        return float(value) if value is not None else None

    @classmethod
    def _period_summary(
        cls,
        series: dict[str, dict[str, float]],
    ) -> dict[str, float | None]:
        def mean_parameter(name: str) -> float | None:
            values = list(series.get(name, {}).values())
            if not values:
                return None
            return cls._mean([float(value) for value in values])

        return {
            "temperature_c": cls._round(mean_parameter("T2M")),
            "humidity_percent": cls._round(mean_parameter("RH2M"), 0),
            "wind_mps": cls._round(mean_parameter("WS10M")),
            "precipitation_mm": cls._round(mean_parameter("PRECTOTCORR")),
        }

    @classmethod
    def _day_summary(
        cls,
        series: dict[str, dict[str, float]],
        day: date,
    ) -> dict[str, float | None]:
        return {
            "temperature_c": cls._round(
                cls._daily_value(series, "T2M", day)
            ),
            "humidity_percent": cls._round(
                cls._daily_value(series, "RH2M", day),
                0,
            ),
            "wind_mps": cls._round(
                cls._daily_value(series, "WS10M", day)
            ),
            "precipitation_mm": cls._round(
                cls._daily_value(series, "PRECTOTCORR", day)
            ),
        }

    @classmethod
    def _aggregate_metrics(
        cls,
        metrics: list[dict[str, float | None]],
    ) -> dict[str, float | None]:
        result: dict[str, float | None] = {}

        for key in (
            "temperature_c",
            "humidity_percent",
            "wind_mps",
            "precipitation_mm",
        ):
            values = [
                float(item[key])
                for item in metrics
                if item.get(key) is not None
            ]

            if not values:
                result[key] = None
                continue

            digits = 0 if key == "humidity_percent" else 1
            result[key] = cls._round(cls._mean(values), digits)

        return result

    @staticmethod
    def _delta(
        value: float | None,
        baseline: float | None,
        digits: int = 1,
    ) -> float | None:
        if value is None or baseline is None:
            return None
        return round(float(value) - float(baseline), digits)

    @classmethod
    def _peak_summary_text(
        cls,
        *,
        peak_metrics: dict[str, float | None],
        period_metrics: dict[str, float | None],
    ) -> str:
        parts = []

        humidity_delta = cls._delta(
            peak_metrics.get("humidity_percent"),
            period_metrics.get("humidity_percent"),
            0,
        )
        temperature_delta = cls._delta(
            peak_metrics.get("temperature_c"),
            period_metrics.get("temperature_c"),
        )
        wind_delta = cls._delta(
            peak_metrics.get("wind_mps"),
            period_metrics.get("wind_mps"),
        )
        rain = peak_metrics.get("precipitation_mm")

        if humidity_delta is not None:
            if humidity_delta <= -8:
                parts.append(
                    f"空气较任务期平均更干，平均湿度低约{abs(int(humidity_delta))}个百分点"
                )
            elif humidity_delta >= 8:
                parts.append(
                    f"空气较任务期平均更湿，平均湿度高约{int(humidity_delta)}个百分点"
                )

        if temperature_delta is not None:
            if temperature_delta >= 2:
                parts.append(
                    f"气温较任务期平均高约{temperature_delta:.1f}℃"
                )
            elif temperature_delta <= -2:
                parts.append(
                    f"气温较任务期平均低约{abs(temperature_delta):.1f}℃"
                )

        if wind_delta is not None and wind_delta >= 1:
            parts.append(
                f"风速较任务期平均高约{wind_delta:.1f} m/s"
            )

        if rain is not None:
            if rain < 1:
                parts.append("当天降水很少")
            elif rain < 5:
                parts.append("当天有少量降水")
            else:
                parts.append("当天有较明显降水")

        if not parts:
            return (
                "峰值日的温度、湿度、风和降水与任务期平均相比没有明显偏离。"
            )

        return "；".join(parts) + "。"

    @classmethod
    def _county_condition(
        cls,
        *,
        peak: dict[str, float | None],
        period: dict[str, float | None],
    ) -> str:
        humidity_delta = cls._delta(
            peak.get("humidity_percent"),
            period.get("humidity_percent"),
            0,
        )
        wind_delta = cls._delta(
            peak.get("wind_mps"),
            period.get("wind_mps"),
        )
        rain = peak.get("precipitation_mm")

        if (
            humidity_delta is not None
            and humidity_delta <= -10
            and (
                rain is None
                or rain < 1
            )
        ):
            return "峰值日相对更干，降水较少"

        if (
            humidity_delta is not None
            and humidity_delta <= -8
        ):
            return "峰值日相对更干"

        if wind_delta is not None and wind_delta >= 1.5:
            return "峰值日风力相对更明显"

        if rain is not None and rain >= 5:
            return "峰值日有较明显降水"

        return "峰值日气象条件接近任务期平均"

    @staticmethod
    def _representative_counties(
        rows: list[dict[str, Any]],
        county_context_service: Any,
        limit: int,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)

        for row in rows:
            try:
                lon = float(row["longitude"])
                lat = float(row["latitude"])
            except (KeyError, TypeError, ValueError):
                continue

            try:
                county = county_context_service.locate_county(lon, lat)
            except (TypeError, ValueError):
                county = None

            if county:
                grouped[str(county)].append((lon, lat))

        ranked = sorted(
            grouped.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )

        result = []

        for county, points in ranked[:limit]:
            result.append(
                {
                    "county_name": county,
                    "fire_count": len(points),
                    "longitude": float(
                        np.median([point[0] for point in points])
                    ),
                    "latitude": float(
                        np.median([point[1] for point in points])
                    ),
                }
            )

        return result

    def analyze(
        self,
        *,
        task_id: str,
        task: dict[str, Any],
        rows: list[dict[str, Any]],
        county_context_service: Any,
    ) -> dict[str, Any]:
        dates = self._task_dates(rows)

        if not dates:
            return self._unavailable("no_task_dates")

        start = min(dates)
        end = max(dates)

        today = datetime.now(timezone.utc).date()

        if end >= today:
            return self._unavailable("not_historical")

        if start < MIN_POWER_DATE:
            return self._unavailable(
                "outside_power_range",
                earliest_supported=MIN_POWER_DATE.isoformat(),
            )

        task_cache = self._task_cache_path(task_id, start, end)

        if task_cache.is_file():
            try:
                return json.loads(task_cache.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        if not getattr(county_context_service, "available", False):
            return self._unavailable("county_context_unavailable")

        counties = self._representative_counties(
            rows,
            county_context_service,
            self.top_counties,
        )

        if not counties:
            return self._unavailable("no_county_locations")

        day_counts = Counter(
            self._date_from_row(row)
            for row in rows
            if self._date_from_row(row) is not None
        )

        peak_day, peak_count = day_counts.most_common(1)[0]

        county_results = []
        period_metrics = []
        peak_metrics = []

        for county in counties:
            payload = self._fetch_power(
                latitude=float(county["latitude"]),
                longitude=float(county["longitude"]),
                start=start,
                end=end,
            )

            if payload is None:
                continue

            series = self._series(payload)

            period = self._period_summary(series)
            peak = self._day_summary(series, peak_day)

            period_metrics.append(period)
            peak_metrics.append(peak)

            county_results.append(
                {
                    **county,
                    "period": period,
                    "peak_day": peak,
                    "condition": self._county_condition(
                        peak=peak,
                        period=period,
                    ),
                }
            )

        if not county_results:
            return self._unavailable("power_unavailable")

        period_average = self._aggregate_metrics(period_metrics)
        peak_average = self._aggregate_metrics(peak_metrics)

        result = {
            "available": True,
            "mode": "historical",
            "source": "NASA POWER Daily",
            "overall": "任务期间天气背景",
            "period": {
                "start": self._display_day(start),
                "end": self._display_day(end),
                "metrics": period_average,
            },
            "peak_day": {
                "date": self._display_day(peak_day),
                "fire_count": int(peak_count),
                "metrics": peak_average,
                "summary": self._peak_summary_text(
                    peak_metrics=peak_average,
                    period_metrics=period_average,
                ),
            },
            "counties": county_results,
            "note": (
                "历史天气用于还原任务期间的气象背景，"
                "不代表预报，也不能单独证明火点成因。"
            ),
        }

        try:
            task_cache.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

        return result
