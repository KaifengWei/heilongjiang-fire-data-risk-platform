"""Evidence-based *relevance*, never confirmation, of agricultural straw burning.

The observation is a FIRMS thermal anomaly, not a ground-confirmed fire type.
MCD12Q1 LC_Type1 provides contextual cropland evidence at ~500 m resolution.
Crop calendar rules are locally supplied, region-specific, and frozen per task.
Confidence/FRP are surfaced as observation evidence but DO NOT identify fuel.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Iterable

from fire_monitor.services.land_cover_context_service import (
    LandCoverContextService,
    PRODUCT_NAME,
    PRODUCT_YEAR,
)

RULE_ID = "agricultural_context_evidence"
RULE_VERSION = "1.0"
LEVELS = ("较高相关", "可能相关", "较低相关", "证据不足")
NOTICE = (
    "本结果为农业秸秆焚烧相关性的线索筛选，不是秸秆焚烧事实认定、"
    "燃烧类型分类模型或火灾发生概率。土地覆盖为500米级2024年背景，"
    "FIRMS观测点与耕地栅格关联不等同于地块级确认。"
)


def validate_calendar_rules(rows: Any) -> list[dict[str, Any]]:
    """Validate independently sourced, explicit local crop-period rules."""
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError("农事时段规则应为不超过500项的数组。")
    result = []
    seen = set()
    for index, item in enumerate(rows, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第{index}项农事规则不是对象。")
        region = str(item.get("region_name") or "").strip()
        crop = str(item.get("crop") or "").strip()
        source = str(item.get("source") or "").strip()
        months = item.get("months")
        if not (1 <= len(region) <= 80 and 1 <= len(crop) <= 80):
            raise ValueError(f"第{index}项必须提供地区名称与作物名称。")
        if len(source) < 4 or len(source) > 250:
            raise ValueError(f"第{index}项必须提供具体农事资料来源。")
        if not isinstance(months, list) or not months or len(months) > 12:
            raise ValueError(f"第{index}项月份应为1至12的非空数组。")
        if any(type(month) is not int or not 1 <= month <= 12 for month in months):
            raise ValueError(f"第{index}项月份必须是1至12的整数。")
        key = (region, crop)
        if key in seen:
            raise ValueError(f"{region}的{crop}存在重复规则。")
        seen.add(key)
        result.append({
            "region_name": region,
            "crop": crop,
            "months": sorted(set(months)),
            "source": source,
        })
    return result


class AgriculturalRelevanceService:
    def __init__(self, land_cover: LandCoverContextService):
        self.land_cover = land_cover

    @staticmethod
    def _calendar_evidence(
        region_name: str, observed_date: str,
        rules: list[dict[str, Any]],
    ) -> tuple[str, list[str], list[str]]:
        applicable = [r for r in rules if r["region_name"] == region_name]
        if not applicable:
            return "not_configured", [], []
        try:
            month = date.fromisoformat(str(observed_date)).month
        except (TypeError, ValueError):
            return "invalid_date", [], []
        matched = [r for r in applicable if month in r["months"]]
        if matched:
            return (
                "in_calendar",
                [r["crop"] for r in matched],
                [r["source"] for r in matched],
            )
        return "outside_calendar", [r["crop"] for r in applicable], [r["source"] for r in applicable]

    def analyze(
        self,
        observations: Iterable[dict[str, Any]],
        *,
        calendar_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rules = validate_calendar_rules(calendar_rules or [])
        rows = list(observations)
        land_installed = self.land_cover._open()
        counts: Counter[str] = Counter()
        by_region: dict[str, Counter[str]] = {}
        agriculture_classes: Counter[str] = Counter()
        calendar_states: Counter[str] = Counter()
        examples: list[dict[str, Any]] = []
        for observation in rows:
            region = str(observation.get("region_name") or "").strip()
            try:
                longitude = float(observation["longitude"])
                latitude = float(observation["latitude"])
            except (ValueError, TypeError, KeyError):
                class_id = None
            else:
                class_id = self.land_cover._sample(longitude, latitude) if land_installed else None

            if class_id == 12:
                surface = "耕地"
                agriculture_classes["cropland"] += 1
            elif class_id == 14:
                surface = "耕地与自然植被混合区"
                agriculture_classes["mosaic"] += 1
            elif class_id is None:
                surface = "无可用土地覆盖数据"
                agriculture_classes["unknown"] += 1
            else:
                surface = "其他地表背景"
                agriculture_classes["other"] += 1

            calendar, crops, sources = self._calendar_evidence(
                region, observation.get("acquired_date"), rules
            )
            calendar_states[calendar] += 1

            # Grading only indicates agreement of the available background
            # evidence. Confidence and FRP cannot establish straw as fuel.
            if class_id == 12 and calendar == "in_calendar":
                level = "较高相关"
                reason = "耕地背景，且处于已配置的当地作物秸秆处理关联月份"
            elif class_id in (12, 14) and calendar == "in_calendar":
                level = "可能相关"
                reason = "耕地混合背景，时间与当地农事规则相符"
            elif class_id == 12 and calendar == "not_configured":
                level = "可能相关"
                reason = "处于耕地背景，尚无该地区的农事时段依据"
            elif class_id in (12, 14) and calendar in ("not_configured", "invalid_date"):
                level = "证据不足"
                reason = "仅有部分农业土地覆盖线索，缺少可靠农事时段判断"
            elif class_id is None:
                level = "证据不足"
                reason = "当前土地覆盖栅格未覆盖此观测位置或数据不可用"
            elif calendar == "outside_calendar" and class_id in (12, 14):
                level = "较低相关"
                reason = "农业地表背景存在，但不在已配置的相关月份内"
            else:
                level = "较低相关"
                reason = "未匹配到耕地或耕地混合背景，需注意栅格尺度局限"

            counts[level] += 1
            if region:
                by_region.setdefault(region, Counter())[level] += 1

            if len(examples) < 20:
                examples.append({
                    "date": str(observation.get("acquired_date") or ""),
                    "region_name": region,
                    "latitude": observation.get("latitude"),
                    "longitude": observation.get("longitude"),
                    "land_cover_class": class_id,
                    "land_cover_label": surface,
                    "calendar_status": calendar,
                    "related_crops": crops,
                    "calendar_sources": sources,
                    "confidence": observation.get("confidence"),
                    "frp": observation.get("frp"),
                    "relevance": level,
                    "reason": reason,
                })

        total = len(rows)
        matched = total - agriculture_classes["unknown"]
        return {
            "available": total > 0,
            "rule_id": RULE_ID,
            "rule_version": RULE_VERSION,
            "disclaimer": NOTICE,
            "total_observations": total,
            "land_cover_available": land_installed,
            "land_cover_product": PRODUCT_NAME,
            "land_cover_year": PRODUCT_YEAR,
            "land_cover_matched": matched,
            "land_cover_coverage": round(matched / total, 4) if total else 0.0,
            "calendar_rules_count": len(rules),
            "calendar_rules_configured": bool(rules),
            "counts": {name: int(counts[name]) for name in LEVELS},
            "land_cover_counts": dict(agriculture_classes),
            "calendar_states": dict(calendar_states),
            "regions": {
                name: {
                    "total": sum(counter.values()),
                    "counts": {level: int(counter[level]) for level in LEVELS},
                }
                for name, counter in sorted(by_region.items())
            },
            "examples": examples,
        }
