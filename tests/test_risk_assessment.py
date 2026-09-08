from __future__ import annotations

import pytest

from fire_monitor.services.risk_assessment_service import (
    RiskAssessmentService,
)


class FakeDatabase:
    def __init__(
        self,
        regions: list[str],
        *,
        task_exists: bool = True,
    ):
        self.regions = regions
        self.task_exists = task_exists

    def get_analysis_task(
        self,
        task_id: str,
    ) -> dict | None:
        if not self.task_exists:
            return None

        return {
            "task_id": task_id,
        }

    def list_regions(
        self,
    ) -> list[dict]:
        return [
            {
                "name": name,
            }
            for name in self.regions
        ]


class FakeStatisticsService:
    def __init__(
        self,
        rows: list[dict],
    ):
        self.rows = rows

    def task_region_statistics(
        self,
        task_id: str,
    ) -> list[dict]:
        return list(
            self.rows
        )


def test_risk_assessment_includes_no_signal_regions():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
                "齐齐哈尔市",
                "牡丹江市",
            ]
        ),
        FakeStatisticsService(
            [
                {
                    "region_name": "哈尔滨市",
                    "active_fire_count": 1,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                }
            ]
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    by_region = {
        row["region_name"]: row
        for row in result["regions"]
    }

    assert (
        by_region["哈尔滨市"][
            "active_fire_count"
        ]
        == 1
    )

    assert (
        by_region["牡丹江市"][
            "active_fire_count"
        ]
        == 0
    )

    assert (
        by_region["牡丹江市"][
            "burned_area_km2"
        ]
        == 0.0
    )

    assert (
        by_region["牡丹江市"][
            "attention_level"
        ]
        == "无遥感信号"
    )

    assert (
        by_region["牡丹江市"][
            "relative_score"
        ]
        is None
    )


def test_equal_evidence_has_equal_attention_level():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
                "齐齐哈尔市",
            ]
        ),
        FakeStatisticsService(
            [
                {
                    "region_name": "哈尔滨市",
                    "active_fire_count": 1,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
                {
                    "region_name": "齐齐哈尔市",
                    "active_fire_count": 1,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
            ]
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    by_region = {
        row["region_name"]: row
        for row in result["regions"]
    }

    harbin = by_region[
        "哈尔滨市"
    ]

    qiqihar = by_region[
        "齐齐哈尔市"
    ]

    assert (
        harbin[
            "active_fire_relative_position"
        ]
        == qiqihar[
            "active_fire_relative_position"
        ]
    )

    assert (
        harbin[
            "relative_score"
        ]
        == qiqihar[
            "relative_score"
        ]
    )

    assert (
        harbin[
            "attention_level"
        ]
        == qiqihar[
            "attention_level"
        ]
    )

    assert (
        harbin[
            "attention_level"
        ]
        == "中关注"
    )


def test_combined_assessment_uses_stronger_relative_signal():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
                "齐齐哈尔市",
                "牡丹江市",
                "大庆市",
            ]
        ),
        FakeStatisticsService(
            [
                {
                    "region_name": "哈尔滨市",
                    "active_fire_count": 4,
                    "burned_pixel_count": 1,
                    "burned_area_km2": 0.1,
                },
                {
                    "region_name": "齐齐哈尔市",
                    "active_fire_count": 1,
                    "burned_pixel_count": 10,
                    "burned_area_km2": 2.0,
                },
                {
                    "region_name": "牡丹江市",
                    "active_fire_count": 2,
                    "burned_pixel_count": 2,
                    "burned_area_km2": 0.4,
                },
                {
                    "region_name": "大庆市",
                    "active_fire_count": 3,
                    "burned_pixel_count": 4,
                    "burned_area_km2": 0.8,
                },
            ]
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    by_region = {
        row["region_name"]: row
        for row in result["regions"]
    }

    qiqihar = by_region[
        "齐齐哈尔市"
    ]

    assert (
        qiqihar[
            "active_fire_relative_position"
        ]
        is not None
    )

    assert (
        qiqihar[
            "burned_area_relative_position"
        ]
        is not None
    )

    assert (
        qiqihar[
            "relative_score"
        ]
        == max(
            qiqihar[
                "active_fire_relative_position"
            ],
            qiqihar[
                "burned_area_relative_position"
            ],
        )
    )

    assert (
        qiqihar[
            "attention_level"
        ]
        == "高关注"
    )


def test_relative_levels_follow_task_distribution():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
                "齐齐哈尔市",
                "牡丹江市",
                "大庆市",
            ]
        ),
        FakeStatisticsService(
            [
                {
                    "region_name": "哈尔滨市",
                    "active_fire_count": 1,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
                {
                    "region_name": "齐齐哈尔市",
                    "active_fire_count": 2,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
                {
                    "region_name": "牡丹江市",
                    "active_fire_count": 3,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
                {
                    "region_name": "大庆市",
                    "active_fire_count": 4,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
            ]
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    by_region = {
        row["region_name"]: row
        for row in result["regions"]
    }

    assert (
        by_region["哈尔滨市"][
            "attention_level"
        ]
        == "低关注"
    )

    assert (
        by_region["齐齐哈尔市"][
            "attention_level"
        ]
        == "中关注"
    )

    assert (
        by_region["牡丹江市"][
            "attention_level"
        ]
        == "较高关注"
    )

    assert (
        by_region["大庆市"][
            "attention_level"
        ]
        == "高关注"
    )


def test_single_positive_region_is_medium_attention():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
                "齐齐哈尔市",
                "牡丹江市",
            ]
        ),
        FakeStatisticsService(
            [
                {
                    "region_name": "哈尔滨市",
                    "active_fire_count": 3,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                }
            ]
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    by_region = {
        row["region_name"]: row
        for row in result["regions"]
    }

    harbin = by_region[
        "哈尔滨市"
    ]

    assert (
        harbin[
            "active_fire_relative_position"
        ]
        == 0.5
    )

    assert (
        harbin[
            "attention_level"
        ]
        == "中关注"
    )


def test_burned_pixel_count_does_not_directly_change_level():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
                "齐齐哈尔市",
            ]
        ),
        FakeStatisticsService(
            [
                {
                    "region_name": "哈尔滨市",
                    "active_fire_count": 0,
                    "burned_pixel_count": 1,
                    "burned_area_km2": 1.0,
                },
                {
                    "region_name": "齐齐哈尔市",
                    "active_fire_count": 0,
                    "burned_pixel_count": 100,
                    "burned_area_km2": 1.0,
                },
            ]
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    by_region = {
        row["region_name"]: row
        for row in result["regions"]
    }

    assert (
        by_region["哈尔滨市"][
            "relative_score"
        ]
        == by_region["齐齐哈尔市"][
            "relative_score"
        ]
    )

    assert (
        by_region["哈尔滨市"][
            "attention_level"
        ]
        == by_region["齐齐哈尔市"][
            "attention_level"
        ]
    )


def test_assessment_contains_rule_metadata_and_disclaimer():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
            ]
        ),
        FakeStatisticsService(
            []
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    assert (
        result["task_id"]
        == "TASK-A"
    )

    assert (
        result["rule_id"]
        == "task_relative_remote_sensing"
    )

    assert (
        result["rule_version"]
        == "1.0"
    )

    assert (
        result["assessment_scope"]
        == "task_relative"
    )

    assert (
        "不代表官方火险等级"
        in result["disclaimer"]
    )

    assert (
        "火灾发生概率"
        in result["disclaimer"]
    )


def test_no_signal_region_has_explanation():
    service = RiskAssessmentService(
        FakeDatabase(
            [
                "哈尔滨市",
            ]
        ),
        FakeStatisticsService(
            []
        ),
    )

    result = service.assess_task(
        "TASK-A"
    )

    row = result["regions"][0]

    assert (
        row["attention_level"]
        == "无遥感信号"
    )

    assert (
        "未出现 FIRMS 主动火点观测记录"
        in row["explanation"]
    )

    assert (
        "MCD64A1"
        in row["explanation"]
    )


def test_unknown_task_is_rejected():
    service = RiskAssessmentService(
        FakeDatabase(
            [],
            task_exists=False,
        ),
        FakeStatisticsService(
            []
        ),
    )

    with pytest.raises(
        KeyError
    ):
        service.assess_task(
            "TASK-NOT-FOUND"
        )