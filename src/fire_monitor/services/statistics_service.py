from __future__ import annotations

from typing import Any

from fire_monitor.storage.database import Database


class StatisticsService:
    """
    市级统计服务。

    基于已有:
    - active_fire_observations
    - burned_pixels

    提供行政区统计结果。
    """

    def __init__(
        self,
        database: Database,
    ):
        self.database = database


    def region_statistics(
        self,
    ) -> list[dict[str, Any]]:
        """
        返回所有已有行政区统计结果。
        """

        with self.database.connect() as conn:

            fire_rows = conn.execute(
                """
                SELECT
                    region_name,
                    COUNT(*) AS active_fire_count
                FROM active_fire_observations
                GROUP BY region_name
                """
            ).fetchall()


            burned_rows = conn.execute(
                """
                SELECT
                    region_name,
                    COUNT(*) AS burned_pixel_count,
                    COALESCE(
                        SUM(cell_area_km2),
                        0
                    ) AS burned_area_km2
                FROM burned_pixels
                GROUP BY region_name
                """
            ).fetchall()


        result: dict[str, dict[str, Any]] = {}


        for row in fire_rows:

            name = row["region_name"]

            if not name:
                continue

            result.setdefault(
                name,
                {
                    "region_name": name,
                    "active_fire_count": 0,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
            )

            result[name][
                "active_fire_count"
            ] = int(
                row["active_fire_count"]
            )


        for row in burned_rows:

            name = row["region_name"]

            if not name:
                continue

            result.setdefault(
                name,
                {
                    "region_name": name,
                    "active_fire_count": 0,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
            )

            result[name][
                "burned_pixel_count"
            ] = int(
                row["burned_pixel_count"]
            )

            result[name][
                "burned_area_km2"
            ] = round(
                float(
                    row["burned_area_km2"]
                ),
                6,
            )


        return sorted(
            result.values(),
            key=lambda x: x["region_name"],
        )


    def region_ranking(
        self,
        *,
        metric: str = "burned_area_km2",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        行政区排名。
        """

        if metric not in {
            "burned_area_km2",
            "active_fire_count",
            "burned_pixel_count",
        }:
            raise ValueError(
                f"不支持的排序指标: {metric}"
            )


        rows = self.region_statistics()

        return sorted(
            rows,
            key=lambda x: x[metric],
            reverse=True,
        )[:limit]