from __future__ import annotations

from typing import Any

from fire_monitor.services.statistics_service import (
    StatisticsService,
)
from fire_monitor.storage.database import Database


RULE_ID = "task_relative_remote_sensing"
RULE_VERSION = "1.0"

DISCLAIMER = (
    "本等级为平台基于当前分析任务遥感观测结果计算的"
    "相对火情关注等级，仅用于任务内行政区之间的比较；"
    "不代表官方火险等级、火灾发生概率或未来火情预测。"
)


class RiskAssessmentService:
    """
    基于当前分析任务正式处理结果，
    计算行政区相对火情关注等级。
    """

    def __init__(
        self,
        database: Database,
        statistics_service: StatisticsService,
    ):
        self.database = database
        self.statistics_service = (
            statistics_service
        )

    @staticmethod
    def _relative_position(
        value: float,
        positive_values: list[float],
    ) -> float | None:
        """
        返回任务内中点相对位置。

        只对正值指标计算；
        不存在正值时返回 None。
        """

        if value <= 0 or not positive_values:
            return None

        smaller = sum(
            1
            for item in positive_values
            if item < value
        )

        equal = sum(
            1
            for item in positive_values
            if item == value
        )

        position = (
            smaller
            + 0.5 * equal
        ) / len(positive_values)

        return round(
            float(position),
            6,
        )

    @staticmethod
    def _attention_level(
        score: float | None,
    ) -> str:
        if score is None:
            return "无遥感信号"

        if score <= 0.25:
            return "低关注"

        if score <= 0.50:
            return "中关注"

        if score <= 0.75:
            return "较高关注"

        return "高关注"

    def assess_task(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.database.get_analysis_task(
            task_id
        )

        if task is None:
            raise KeyError(
                f"分析任务不存在：{task_id}"
            )

        statistics = (
            self.statistics_service
            .task_region_statistics(
                task_id
            )
        )

        statistics_by_region = {
            row["region_name"]: row
            for row in statistics
        }

        region_names = sorted(
            {
                row["name"]
                for row
                in self.database.list_regions()
                if row["name"]
            }
            | set(
                statistics_by_region.keys()
            )
        )

        rows: list[dict[str, Any]] = []

        for region_name in region_names:
            source = statistics_by_region.get(
                region_name,
                {},
            )

            rows.append(
                {
                    "region_name": region_name,
                    "active_fire_count": int(
                        source.get(
                            "active_fire_count",
                            0,
                        )
                    ),
                    "burned_pixel_count": int(
                        source.get(
                            "burned_pixel_count",
                            0,
                        )
                    ),
                    "burned_area_km2": round(
                        float(
                            source.get(
                                "burned_area_km2",
                                0.0,
                            )
                        ),
                        6,
                    ),
                }
            )

        active_values = [
            float(
                row["active_fire_count"]
            )
            for row in rows
            if row["active_fire_count"] > 0
        ]

        burned_values = [
            float(
                row["burned_area_km2"]
            )
            for row in rows
            if row["burned_area_km2"] > 0
        ]

        results: list[dict[str, Any]] = []

        for row in rows:
            active_position = (
                self._relative_position(
                    float(
                        row[
                            "active_fire_count"
                        ]
                    ),
                    active_values,
                )
            )

            burned_position = (
                self._relative_position(
                    float(
                        row[
                            "burned_area_km2"
                        ]
                    ),
                    burned_values,
                )
            )

            available_positions = [
                value
                for value in (
                    active_position,
                    burned_position,
                )
                if value is not None
            ]

            score = (
                max(available_positions)
                if available_positions
                else None
            )

            level = (
                self._attention_level(
                    score
                )
            )

            evidence: list[str] = []

            if row["active_fire_count"] > 0:
                evidence.append(
                    "FIRMS 主动火点观测记录"
                    f" {row['active_fire_count']} 条"
                )

            if row["burned_area_km2"] > 0:
                evidence.append(
                    "MCD64A1 烧毁像元面积估计"
                    f" {row['burned_area_km2']:.6f} km²"
                )

            if not evidence:
                explanation = (
                    "当前任务中该行政区"
                    "未出现 FIRMS 主动火点观测记录，"
                    "也未出现 MCD64A1"
                    " 烧毁像元面积估计。"
                )
            else:
                explanation = (
                    "；".join(evidence)
                    + "。最终等级取当前任务内"
                    "可用遥感指标相对位置中的较高值。"
                )

            results.append(
                {
                    **row,
                    "active_fire_relative_position": (
                        active_position
                    ),
                    "burned_area_relative_position": (
                        burned_position
                    ),
                    "relative_score": score,
                    "attention_level": level,
                    "explanation": explanation,
                }
            )

        return {
            "task_id": task_id,
            "rule_id": RULE_ID,
            "rule_version": RULE_VERSION,
            "assessment_scope": (
                "task_relative"
            ),
            "disclaimer": DISCLAIMER,
            "regions": results,
        }