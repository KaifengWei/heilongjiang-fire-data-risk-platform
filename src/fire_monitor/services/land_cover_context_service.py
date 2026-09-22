"""Task-level land-cover context for FIRMS observations."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

try:
    from osgeo import gdal, osr  # type: ignore
except ImportError:
    gdal = None
    osr = None


PRODUCT_NAME = "MCD12Q1 V061"
PRODUCT_YEAR = 2024
PRODUCT_LAYER = "LC_Type1"

IGBP_GROUPS = {
    1: "forest", 2: "forest", 3: "forest", 4: "forest", 5: "forest",
    6: "grass_shrub", 7: "grass_shrub", 8: "grass_shrub",
    9: "grass_shrub", 10: "grass_shrub",
    11: "wetland_water",
    12: "agriculture",
    13: "urban",
    14: "agriculture",
    15: "barren_snow", 16: "barren_snow",
    17: "wetland_water",
}

GROUP_LABELS = {
    "agriculture": "农田背景",
    "forest": "林地背景",
    "grass_shrub": "草地/灌丛背景",
    "wetland_water": "湿地/水体背景",
    "urban": "城镇建设用地背景",
    "barren_snow": "裸地/冰雪背景",
    "mixed": "多种地表类型混合",
}


class LandCoverContextService:
    def __init__(
        self,
        raster_path: str | Path,
        *,
        minimum_coverage: float = 0.80,
    ):
        self.raster_path = Path(raster_path)
        self.minimum_coverage = float(minimum_coverage)
        self._dataset = None
        self._array = None
        self._inverse = None
        self._transform = None
        self._nodata = None

    @staticmethod
    def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "available": False,
            "reason": reason,
            "product": PRODUCT_NAME,
            "year": PRODUCT_YEAR,
            **extra,
        }

    def _open(self) -> bool:
        if self._dataset is not None:
            return True

        if gdal is None or osr is None or not self.raster_path.is_file():
            return False

        dataset = gdal.Open(str(self.raster_path), gdal.GA_ReadOnly)
        if dataset is None:
            return False

        band = dataset.GetRasterBand(1)
        array = band.ReadAsArray()
        if array is None:
            return False

        inverse = gdal.InvGeoTransform(dataset.GetGeoTransform())

        if (
            isinstance(inverse, tuple)
            and len(inverse) == 2
            and isinstance(inverse[0], (bool, int))
        ):
            if not inverse[0]:
                return False
            inverse = inverse[1]

        if not isinstance(inverse, tuple) or len(inverse) != 6:
            return False

        projection = dataset.GetProjection()
        if not projection:
            return False

        source_srs = osr.SpatialReference()
        source_srs.ImportFromWkt(projection)

        wgs84 = osr.SpatialReference()
        wgs84.ImportFromEPSG(4326)

        if hasattr(source_srs, "SetAxisMappingStrategy"):
            source_srs.SetAxisMappingStrategy(
                osr.OAMS_TRADITIONAL_GIS_ORDER
            )
            wgs84.SetAxisMappingStrategy(
                osr.OAMS_TRADITIONAL_GIS_ORDER
            )

        transform = None
        if not source_srs.IsSame(wgs84):
            transform = osr.CoordinateTransformation(wgs84, source_srs)

        self._dataset = dataset
        self._array = np.asarray(array)
        self._inverse = tuple(inverse)
        self._transform = transform
        self._nodata = band.GetNoDataValue()
        return True

    def _sample(self, longitude: float, latitude: float) -> int | None:
        if not self._open():
            return None

        x = float(longitude)
        y = float(latitude)

        if self._transform is not None:
            try:
                x, y, _ = self._transform.TransformPoint(x, y)
            except (TypeError, RuntimeError):
                return None

        inv = self._inverse
        pixel = int(inv[0] + inv[1] * x + inv[2] * y)
        line = int(inv[3] + inv[4] * x + inv[5] * y)

        if (
            pixel < 0
            or line < 0
            or line >= self._array.shape[0]
            or pixel >= self._array.shape[1]
        ):
            return None

        value = int(self._array[line, pixel])

        if self._nodata is not None and value == int(self._nodata):
            return None

        return value if value in IGBP_GROUPS else None

    @staticmethod
    def _guidance(group: str, mixed: bool) -> str:
        if mixed:
            return (
                "本次火点分布涉及多种地表类型，"
                "建议结合重点地区和持续活跃位置分区核查。"
            )
        if group == "agriculture":
            return (
                "本次可识别火点以农田及农田—自然植被交错背景为主，"
                "建议重点核查农田区域的热异常来源。"
            )
        if group == "forest":
            return (
                "本次可识别火点以林地背景为主，"
                "建议重点核查林地区域的持续活跃位置。"
            )
        if group == "grass_shrub":
            return (
                "本次可识别火点以草地和灌丛背景为主，"
                "建议重点核查这些区域的重复活跃位置。"
            )
        if group == "urban":
            return (
                "本次可识别火点中城镇建设用地背景较突出，"
                "建议优先核查固定热源和生产活动较集中的位置。"
            )
        if group == "wetland_water":
            return (
                "本次可识别火点中湿地和水体周边背景较突出，"
                "建议结合具体位置核查岸线及邻近区域热异常。"
            )
        return (
            "本次火点地表背景较分散，"
            "建议结合重点地区和持续活跃位置进一步核查。"
        )

    @classmethod
    def _summary(cls, counter: Counter[str]) -> dict[str, Any] | None:
        total = int(sum(counter.values()))
        if total <= 0:
            return None

        group, count = counter.most_common(1)[0]
        share = float(count) / float(total)
        mixed = share < 0.45

        display_group = "mixed" if mixed else group
        visual_title = (
            "地表类型较分散"
            if mixed
            else f"{GROUP_LABELS[group]}为主"
        )

        return {
            "matched_count": total,
            "dominant_group": display_group,
            "dominant_label": GROUP_LABELS[display_group],
            "visual_title": visual_title,
            "dominant_share": round(share, 4),
            "guidance": cls._guidance(group, mixed),
            "counts": dict(counter),
        }


    @classmethod
    def build_priority_guidance(
        cls,
        analysis: dict[str, Any],
        priority_regions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not analysis or not analysis.get("available"):
            return None

        regions = analysis.get("regions") or {}
        items = []

        for row in priority_regions or []:
            region_name = str(row.get("region_name") or "").strip()
            if not region_name:
                continue

            context = regions.get(region_name)
            if not context:
                continue

            items.append(
                {
                    "region_name": region_name,
                    "dominant_group": context.get("dominant_group"),
                    "dominant_label": context.get("dominant_label"),
                }
            )

        if not items:
            return None

        usable_groups = [
            item["dominant_group"]
            for item in items
            if item.get("dominant_group")
            and item.get("dominant_group") != "mixed"
        ]

        common_group = None

        if usable_groups and len(set(usable_groups)) == 1:
            common_group = usable_groups[0]

        if common_group == "agriculture":
            message = (
                "这些重点地区的火点活动较往年同期更突出，"
                "且可识别火点主要位于农田背景区域，"
                "建议优先核查农田区域的热异常来源。"
            )
        elif common_group == "forest":
            message = (
                "这些重点地区的火点活动较往年同期更突出，"
                "且可识别火点主要位于林地背景区域，"
                "建议优先核查林地区域的持续活跃位置。"
            )
        elif common_group == "grass_shrub":
            message = (
                "这些重点地区的火点活动较往年同期更突出，"
                "且可识别火点主要位于草地和灌丛背景区域，"
                "建议优先核查重复活跃位置。"
            )
        elif common_group == "urban":
            message = (
                "这些重点地区的火点活动较往年同期更突出，"
                "其中城镇建设用地背景较明显，"
                "建议优先核查固定热源及生产活动集中位置。"
            )
        else:
            message = (
                "这些重点地区的火点活动较往年同期更突出，"
                "各地地表背景存在差异，"
                "建议结合各地区主要地表类型分别核查。"
            )

        return {
            "items": items,
            "common_group": common_group,
            "message": message,
        }

    def analyze(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not self._open():
            return self._unavailable("land_cover_not_installed")

        if not rows:
            return self._unavailable("no_current_observations")

        total = 0
        matched = 0
        overall = Counter()
        by_region: dict[str, Counter[str]] = {}

        for row in rows:
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            total += 1
            class_id = self._sample(longitude, latitude)
            if class_id is None:
                continue

            matched += 1
            group = IGBP_GROUPS[class_id]
            overall[group] += 1

            region = str(row.get("region_name") or "").strip()
            if region:
                by_region.setdefault(region, Counter())[group] += 1

        if total <= 0:
            return self._unavailable("no_valid_coordinates")

        coverage = matched / total

        if coverage < self.minimum_coverage:
            return self._unavailable(
                "insufficient_land_cover_coverage",
                coverage_ratio=round(coverage, 4),
            )

        summary = self._summary(overall)
        if summary is None:
            return self._unavailable("no_land_cover_matches")

        regions = {}
        for region, counter in by_region.items():
            item = self._summary(counter)
            if item is not None:
                regions[region] = item

        return {
            "available": True,
            "product": PRODUCT_NAME,
            "year": PRODUCT_YEAR,
            "layer": PRODUCT_LAYER,
            "total_observations": total,
            "matched_observations": matched,
            "coverage_ratio": round(coverage, 4),
            "dominant_group": summary["dominant_group"],
            "dominant_label": summary["dominant_label"],
            "visual_title": summary["visual_title"],
            "dominant_share": summary["dominant_share"],
            "guidance": summary["guidance"],
            "counts": summary["counts"],
            "regions": regions,
        }
