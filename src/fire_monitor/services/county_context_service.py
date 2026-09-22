"""County/district boundary context for map drill-down."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape
from shapely.strtree import STRtree


CITY_CODE_NAMES = {
    "2301": "哈尔滨市",
    "2302": "齐齐哈尔市",
    "2303": "鸡西市",
    "2304": "鹤岗市",
    "2305": "双鸭山市",
    "2306": "大庆市",
    "2307": "伊春市",
    "2308": "佳木斯市",
    "2309": "七台河市",
    "2310": "牡丹江市",
    "2311": "黑河市",
    "2312": "绥化市",
    "2327": "大兴安岭地区",
}


class CountyContextService:
    """Load compact county boundaries and locate FIRMS points on demand."""

    def __init__(self, geojson_path: str | Path):
        self.geojson_path = Path(geojson_path)
        self._loaded = False
        self._features: list[dict[str, Any]] = []
        self._geometries = []
        self._tree: STRtree | None = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return bool(self._features)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        self._loaded = True

        if not self.geojson_path.is_file():
            return

        payload = json.loads(
            self.geojson_path.read_text(encoding="utf-8")
        )

        if payload.get("type") != "FeatureCollection":
            return

        features = []
        geometries = []

        for feature in payload.get("features", []):
            properties = feature.get("properties") or {}
            geometry_json = feature.get("geometry")
            name = str(properties.get("name") or "").strip()
            pac = str(
                properties.get("pac")
                or properties.get("PAC")
                or ""
            ).strip()
            city_name = str(
                properties.get("city_name")
                or ""
            ).strip()

            if not name or not geometry_json:
                continue

            try:
                geometry = shape(geometry_json)
            except (TypeError, ValueError):
                continue

            if geometry.is_empty:
                continue

            if not city_name and len(pac) >= 4:
                city_name = CITY_CODE_NAMES.get(
                    pac[:4],
                    "",
                )

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "name": name,
                        "pac": pac,
                        "city_name": city_name,
                    },
                    "geometry": geometry_json,
                }
            )
            geometries.append(geometry)

        if not features:
            return

        self._features = features
        self._geometries = geometries
        self._tree = STRtree(geometries)

    def locate_county(
        self,
        longitude: float,
        latitude: float,
    ) -> str | None:
        self._ensure_loaded()

        if self._tree is None:
            return None

        point = Point(
            float(longitude),
            float(latitude),
        )

        candidate_indexes = self._tree.query(
            point,
            predicate="intersects",
        )

        for index in candidate_indexes:
            feature = self._features[int(index)]
            return str(
                feature["properties"]["name"]
            )

        return None

    def feature_collection_for_city(
        self,
        city_name: str,
    ) -> dict[str, Any]:
        self._ensure_loaded()

        selected = [
            feature
            for feature in self._features
            if (
                feature["properties"]
                .get("city_name")
                == city_name
            )
        ]

        return {
            "type": "FeatureCollection",
            "features": selected,
        }
