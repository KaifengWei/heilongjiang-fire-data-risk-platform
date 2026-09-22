"""NOAA GFS short-range weather context for recent FIRMS tasks."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from osgeo import gdal


gdal.UseExceptions()

FILTER_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
FORECAST_HOURS = (24, 48, 72)
BBOX = (120, 42, 136, 55)


class GfsWeatherContextService:
    def __init__(self, cache_dir: str | Path, *, recent_days: int = 2):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.recent_days = int(recent_days)

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {"available": False, "reason": reason}

    @staticmethod
    def _task_end_date(task: dict[str, Any], rows: list[dict[str, Any]]) -> date | None:
        raw = str(task.get("analysis_end") or "")[:10]
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass

        values = []
        for row in rows:
            raw = str(row.get("acquired_date") or "")[:10]
            if not raw:
                continue
            try:
                values.append(date.fromisoformat(raw))
            except ValueError:
                continue

        return max(values) if values else None

    def task_is_recent(
        self,
        task: dict[str, Any],
        rows: list[dict[str, Any]],
        *,
        today: date | None = None,
    ) -> bool:
        end_date = self._task_end_date(task, rows)
        if end_date is None:
            return False

        current = today or datetime.now(timezone.utc).date()
        delta = (current - end_date).days
        return -1 <= delta <= self.recent_days

    @staticmethod
    def _candidate_cycles() -> list[tuple[str, str]]:
        now = datetime.now(timezone.utc)
        result = []

        for hours_back in range(0, 43, 6):
            dt = now - timedelta(hours=hours_back)
            hour = (dt.hour // 6) * 6
            cycle = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
            item = (cycle.strftime("%Y%m%d"), cycle.strftime("%H"))
            if item not in result:
                result.append(item)

        return result

    @staticmethod
    def _params(day: str, cycle: str, forecast_hour: int) -> dict[str, str]:
        left, bottom, right, top = BBOX
        return {
            "file": f"gfs.t{cycle}z.pgrb2.0p25.f{forecast_hour:03d}",
            "var_TMP": "on",
            "var_RH": "on",
            "var_UGRD": "on",
            "var_VGRD": "on",
            "var_APCP": "on",
            "lev_2_m_above_ground": "on",
            "lev_10_m_above_ground": "on",
            "lev_surface": "on",
            "subregion": "",
            "leftlon": str(left),
            "rightlon": str(right),
            "toplat": str(top),
            "bottomlat": str(bottom),
            "dir": f"/gfs.{day}/{cycle}/atmos",
        }

    def _cache_path(self, day: str, cycle: str, forecast_hour: int) -> Path:
        return self.cache_dir / (
            f"gfs_{day}_{cycle}z_f{forecast_hour:03d}_hlj.grib2"
        )

    def _download(
        self,
        session: requests.Session,
        day: str,
        cycle: str,
        forecast_hour: int,
    ) -> Path | None:
        target = self._cache_path(day, cycle, forecast_hour)

        if target.is_file() and target.stat().st_size > 1000:
            return target

        try:
            response = session.get(
                FILTER_URL,
                params=self._params(day, cycle, forecast_hour),
                timeout=90,
            )
        except requests.RequestException:
            return None

        content_type = response.headers.get("Content-Type", "").lower()

        if (
            response.status_code != 200
            or len(response.content) < 1000
            or "text/html" in content_type
        ):
            return None

        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(response.content)
        partial.replace(target)
        return target

    def _load_bundle(self) -> tuple[str, str, dict[int, Path]] | None:
        session = requests.Session()
        session.headers.update(
            {"User-Agent": "heilongjiang-fire-monitor/gfs-weather-context"}
        )

        for day, cycle in self._candidate_cycles():
            bundle = {}

            for forecast_hour in FORECAST_HOURS:
                path = self._download(session, day, cycle, forecast_hour)
                if path is None:
                    bundle = {}
                    break
                bundle[forecast_hour] = path

            if bundle:
                return day, cycle, bundle

        return None

    @staticmethod
    def _apcp_priority(element: str) -> int:
        if not element.startswith("APCP"):
            return -1

        suffix = element[4:]

        try:
            return int(suffix)
        except ValueError:
            return 0

    @classmethod
    def _read_fields(cls, path: Path) -> dict[str, Any]:
        dataset = gdal.Open(str(path), gdal.GA_ReadOnly)
        if dataset is None:
            raise RuntimeError(f"Could not open {path.name}")

        inverse = gdal.InvGeoTransform(dataset.GetGeoTransform())

        if (
            isinstance(inverse, tuple)
            and len(inverse) == 2
            and isinstance(inverse[0], (bool, int))
        ):
            if not inverse[0]:
                raise RuntimeError("Invalid GFS transform.")
            inverse = inverse[1]

        if not isinstance(inverse, tuple) or len(inverse) != 6:
            raise RuntimeError("Invalid GFS transform.")

        fields: dict[str, Any] = {
            "dataset": dataset,
            "inverse": tuple(inverse),
        }
        apcp = []

        for index in range(1, dataset.RasterCount + 1):
            band = dataset.GetRasterBand(index)
            metadata = band.GetMetadata()
            element = str(metadata.get("GRIB_ELEMENT", ""))
            short_name = str(metadata.get("GRIB_SHORT_NAME", ""))

            item = {
                "array": np.asarray(band.ReadAsArray(), dtype=float),
                "nodata": band.GetNoDataValue(),
            }

            if element == "TMP" and short_name == "2-HTGL":
                fields["temperature"] = item
            elif element == "RH" and short_name == "2-HTGL":
                fields["humidity"] = item
            elif element == "UGRD" and short_name == "10-HTGL":
                fields["u_wind"] = item
            elif element == "VGRD" and short_name == "10-HTGL":
                fields["v_wind"] = item
            elif element.startswith("APCP") and short_name == "0-SFC":
                apcp.append((cls._apcp_priority(element), item))

        for required in ("temperature", "humidity", "u_wind", "v_wind"):
            if required not in fields:
                raise RuntimeError(f"Missing GFS field: {required}")

        if apcp:
            apcp.sort(key=lambda row: row[0], reverse=True)
            fields["precipitation"] = apcp[0][1]
        else:
            fields["precipitation"] = None

        return fields

    @staticmethod
    def _sample(fields: dict[str, Any], key: str, lon: float, lat: float) -> float | None:
        item = fields.get(key)
        if item is None:
            return None

        inv = fields["inverse"]
        pixel = int(inv[0] + inv[1] * lon + inv[2] * lat)
        line = int(inv[3] + inv[4] * lon + inv[5] * lat)

        array = item["array"]

        if (
            pixel < 0
            or line < 0
            or line >= array.shape[0]
            or pixel >= array.shape[1]
        ):
            return None

        value = float(array[line, pixel])
        nodata = item.get("nodata")

        if nodata is not None and value == float(nodata):
            return None

        return value if np.isfinite(value) else None

    @classmethod
    def _sample_point(cls, fields: dict[str, Any], lon: float, lat: float) -> dict[str, float] | None:
        temperature = cls._sample(fields, "temperature", lon, lat)
        humidity = cls._sample(fields, "humidity", lon, lat)
        u_wind = cls._sample(fields, "u_wind", lon, lat)
        v_wind = cls._sample(fields, "v_wind", lon, lat)
        precipitation = cls._sample(fields, "precipitation", lon, lat)

        if any(value is None for value in (temperature, humidity, u_wind, v_wind)):
            return None

        return {
            "temperature": float(temperature),
            "humidity": float(humidity),
            "wind_speed": float(np.hypot(u_wind, v_wind)),
            "precipitation": float(precipitation or 0.0),
        }

    @staticmethod
    def evaluate_conditions(
        *,
        temperature: float,
        humidity: float,
        wind_speed: float,
        precipitation: float,
    ) -> dict[str, str]:
        if precipitation >= 10.0:
            return {
                "state": "条件明显趋缓",
                "tone": "easing",
                "summary": "预计有较明显降水，当前已有火点附近的持续活跃条件将有所减弱。",
            }

        if precipitation >= 5.0:
            return {
                "state": "条件趋缓",
                "tone": "easing",
                "summary": "预计有一定降水，当前已有火点附近的持续活跃条件有所缓和。",
            }

        if humidity <= 35.0 and wind_speed >= 6.0:
            return {
                "state": "建议提高关注",
                "tone": "alert",
                "summary": "空气偏干且风力较明显，当前已有火点附近建议重点关注持续活跃位置。",
            }

        if humidity <= 35.0 or (humidity <= 45.0 and wind_speed >= 4.0):
            return {
                "state": "建议继续关注",
                "tone": "watch",
                "summary": "空气偏干，部分已有火点附近仍值得持续关注。",
            }

        if wind_speed >= 6.0:
            return {
                "state": "建议继续关注",
                "tone": "watch",
                "summary": "风力较明显，建议继续关注当前活跃位置的变化。",
            }

        return {
            "state": "条件相对平稳",
            "tone": "normal",
            "summary": "未来气象条件整体较平稳，按当前重点区域持续查看即可。",
        }

    @classmethod
    def _summarize(cls, samples: list[dict[str, float]]) -> dict[str, Any] | None:
        if not samples:
            return None

        def median(key: str) -> float:
            return float(np.median([row[key] for row in samples]))

        temperature = median("temperature")
        humidity = median("humidity")
        wind_speed = median("wind_speed")
        precipitation = median("precipitation")

        judgement = cls.evaluate_conditions(
            temperature=temperature,
            humidity=humidity,
            wind_speed=wind_speed,
            precipitation=precipitation,
        )

        return {
            **judgement,
            "temperature_c": round(temperature, 1),
            "humidity_percent": round(humidity, 0),
            "wind_mps": round(wind_speed, 1),
            "precipitation_mm": round(precipitation, 1),
        }

    @staticmethod
    def combine_horizon_guidance(
        province_summary: dict[str, Any],
        county_rows: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Let localized active-county conditions influence user-facing guidance."""

        order = {
            "alert": 0,
            "watch": 1,
            "normal": 2,
            "easing": 3,
        }

        result = {
            "tone": str(province_summary.get("tone") or "normal"),
            "state": str(
                province_summary.get("state")
                or "条件相对平稳"
            ),
            "summary": str(
                province_summary.get("summary")
                or ""
            ),
        }

        if not county_rows:
            return result

        strongest = min(
            county_rows,
            key=lambda row: order.get(
                str(row.get("tone") or ""),
                4,
            ),
        )

        county_tone = str(
            strongest.get("tone")
            or ""
        )

        province_tone = result["tone"]

        if order.get(county_tone, 4) >= order.get(province_tone, 4):
            return result

        names = [
            str(row.get("county_name") or "")
            for row in county_rows
            if str(row.get("tone") or "") == county_tone
            and str(row.get("county_name") or "")
        ][:3]

        joined = "、".join(names)

        if county_tone == "alert":
            return {
                "tone": "alert",
                "state": "局部需提高关注",
                "summary": (
                    "全省总体条件未明显偏强，"
                    f"但{joined}等当前活跃县区空气偏干或风力较明显，"
                    "建议优先查看这些区域。"
                ),
            }

        if county_tone == "watch":
            return {
                "tone": "watch",
                "state": "局部建议继续关注",
                "summary": (
                    "全省总体条件较平稳，"
                    f"但{joined}等当前活跃县区仍有偏干或风力较明显的情况，"
                    "建议继续关注这些区域。"
                ),
            }

        return result

    def analyze(
        self,
        *,
        task: dict[str, Any],
        rows: list[dict[str, Any]],
        county_context_service: Any = None,
    ) -> dict[str, Any]:
        if not self.task_is_recent(task, rows):
            return self._unavailable("historical_task")

        if not rows:
            return self._unavailable("no_current_observations")

        bundle = self._load_bundle()
        if bundle is None:
            return self._unavailable("gfs_unavailable")

        day, cycle, paths = bundle

        try:
            forecasts = {
                hour: self._read_fields(path)
                for hour, path in paths.items()
            }
        except (RuntimeError, OSError):
            return self._unavailable("gfs_parse_failed")

        prepared = []
        county_counts = Counter()

        county_available = bool(
            county_context_service
            and getattr(county_context_service, "available", False)
        )

        for row in rows:
            try:
                lon = float(row["longitude"])
                lat = float(row["latitude"])
            except (KeyError, TypeError, ValueError):
                continue

            county = None

            if county_available:
                try:
                    county = county_context_service.locate_county(lon, lat)
                except (TypeError, ValueError):
                    county = None

            if county:
                county_counts[county] += 1

            prepared.append((lon, lat, county))

        top_counties = [name for name, _ in county_counts.most_common(3)]
        horizons = []

        for hour in FORECAST_HOURS:
            fields = forecasts[hour]
            all_samples = []
            by_county: dict[str, list[dict[str, float]]] = defaultdict(list)

            for lon, lat, county in prepared:
                sample = self._sample_point(fields, lon, lat)
                if sample is None:
                    continue

                all_samples.append(sample)

                if county in top_counties:
                    by_county[county].append(sample)

            summary = self._summarize(all_samples)
            if summary is None:
                continue

            county_rows = []

            for county in top_counties:
                county_summary = self._summarize(by_county.get(county, []))
                if county_summary is None:
                    continue

                county_rows.append(
                    {
                        "county_name": county,
                        "fire_count": county_counts[county],
                        **county_summary,
                    }
                )

            guidance = self.combine_horizon_guidance(
                summary,
                county_rows,
            )

            horizons.append(
                {
                    "hours": hour,
                    **summary,
                    **guidance,
                    "counties": county_rows,
                }
            )

        if not horizons:
            return self._unavailable("no_weather_samples")

        order = {"alert": 0, "watch": 1, "normal": 2, "easing": 3}
        strongest = min(horizons, key=lambda row: order.get(row["tone"], 4))

        overall = {
            "alert": "未来天气需提高关注",
            "watch": "未来天气建议继续关注",
            "normal": "未来天气整体平稳",
            "easing": "未来天气条件趋缓",
        }.get(strongest["tone"], "未来天气条件已更新")

        return {
            "available": True,
            "source": "NOAA GFS 0.25°",
            "cycle": f"{day} {cycle}Z",
            "overall": overall,
            "horizons": horizons,
        }
