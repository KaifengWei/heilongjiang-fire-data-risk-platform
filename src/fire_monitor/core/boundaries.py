"""GeoJSON 行政区读取与轻量点落区计算。

这里故意不把行政区名称写死在代码中。系统可加载任意省、市、县级
GeoJSON；导入点和栅格后，通过边界几何给记录赋予区域名称。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


try:
    from osgeo import ogr as _OGR  # type: ignore
except ImportError:  # 普通 CSV/GeoJSON 运行环境可以没有 GDAL。
    _OGR = None


EPSILON = 1e-10


def _point_on_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> bool:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > EPSILON:
        return False
    return (
        min(x1, x2) - EPSILON <= px <= max(x1, x2) + EPSILON
        and min(y1, y2) - EPSILON <= py <= max(y1, y2) + EPSILON
    )


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """射线法判断点是否在环内，边界视为在区域内。"""
    if len(ring) < 3:
        return False
    inside = False
    point = (lon, lat)
    previous = tuple(ring[-1])
    for raw_current in ring:
        current = tuple(raw_current)
        if _point_on_segment(point, previous, current):
            return True
        x1, y1 = previous
        x2, y2 = current
        intersects = (y1 > lat) != (y2 > lat)
        if intersects:
            x_at_lat = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < x_at_lat:
                inside = not inside
        previous = current
    return inside


def point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(lon, lat, polygon[0]):
        return False
    # GeoJSON 中首环是外边界，之后的环是洞。
    return not any(point_in_ring(lon, lat, hole) for hole in polygon[1:])


def geometry_contains(geometry: dict[str, Any], lon: float, lat: float) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return point_in_polygon(lon, lat, coordinates)
    if geometry_type == "MultiPolygon":
        return any(point_in_polygon(lon, lat, polygon) for polygon in coordinates)
    if geometry_type == "GeometryCollection":
        return any(geometry_contains(item, lon, lat) for item in geometry.get("geometries", []))
    raise ValueError(f"不支持的 GeoJSON 几何类型：{geometry_type}")


def _walk_coordinate_pairs(value: Any, pairs: list[tuple[float, float]]) -> None:
    if not isinstance(value, list):
        return
    if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
        pairs.append((float(value[0]), float(value[1])))
        return
    for child in value:
        _walk_coordinate_pairs(child, pairs)


def geometry_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    pairs: list[tuple[float, float]] = []
    if geometry.get("type") == "GeometryCollection":
        for item in geometry.get("geometries", []):
            _walk_coordinate_pairs(item.get("coordinates"), pairs)
    else:
        _walk_coordinate_pairs(geometry.get("coordinates"), pairs)
    if not pairs:
        raise ValueError("无法从 GeoJSON 几何对象计算边界范围。")
    lons, lats = zip(*pairs)
    return min(lons), min(lats), max(lons), max(lats)


def _try_create_ogr_geometry(geometry: dict[str, Any]) -> Any | None:
    """有 GDAL 时使用 C++ 几何引擎加速大规模点落区；没有则纯 Python 兜底。"""
    try:
        if _OGR is None:
            return None
        return _OGR.CreateGeometryFromJson(json.dumps(geometry, ensure_ascii=False))
    except (AttributeError, TypeError, ValueError):
        return None


def feature_collection_geometry(features: Iterable[dict[str, Any]]) -> dict[str, Any]:
    geometries = [feature["geometry"] for feature in features if feature.get("geometry")]
    if not geometries:
        raise ValueError("GeoJSON 中没有可用的几何对象。")
    if len(geometries) == 1:
        return geometries[0]
    return {"type": "GeometryCollection", "geometries": geometries}


def _get_feature_name(feature: dict[str, Any], name_field: str) -> str:
    props = feature.get("properties") or {}
    value = props.get(name_field)
    if value is None or not str(value).strip():
        raise ValueError(f"GeoJSON 要素缺少名称字段“{name_field}”。")
    return str(value).strip()


def load_regions_from_geojson(
    path: str | Path,
    *,
    source: str | None = None,
    version: str | None = None,
    name_field: str | None = None,
    region_name: str | None = None,
    level: str = "city",
) -> list[dict[str, Any]]:
    """读取区域边界。

    - ``region_name``：把文件的全部要素合并为一个区域，适合一个城市由多个区县
      组成的 GeoJSON；
    - ``name_field``：按属性字段把一个 GeoJSON 拆成多个区域，适合 GADM 等数据。
    """
    geojson_path = Path(path)
    payload = json.loads(geojson_path.read_text(encoding="utf-8-sig"))
    if payload.get("type") == "FeatureCollection":
        features = payload.get("features", [])
    elif payload.get("type") == "Feature":
        features = [payload]
    else:
        features = [{"type": "Feature", "properties": {}, "geometry": payload}]
    if not features:
        raise ValueError(f"边界文件为空：{geojson_path}")

    source_text = source or geojson_path.name
    if region_name:
        return [
            {
                "name": region_name,
                "level": level,
                "geometry": feature_collection_geometry(features),
                "source": source_text,
                "version": version,
            }
        ]

    if not name_field:
        raise ValueError("一个 GeoJSON 包含多个区域时，请指定 --name-field；单区域文件请指定 --region-name。")

    groups: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        groups.setdefault(_get_feature_name(feature, name_field), []).append(feature)
    return [
        {
            "name": name,
            "level": level,
            "geometry": feature_collection_geometry(group),
            "source": source_text,
            "version": version,
        }
        for name, group in groups.items()
    ]


@dataclass
class RegionIndex:
    """按导入顺序确定重叠边界像元的唯一归属。"""

    regions: list[dict[str, Any]]

    def __post_init__(self) -> None:
        self._bounds = [geometry_bounds(region["geometry"]) for region in self.regions]
        self._ogr_geometries = [_try_create_ogr_geometry(region["geometry"]) for region in self.regions]

    @staticmethod
    def _in_bounds(lon: float, lat: float, bounds: tuple[float, float, float, float]) -> bool:
        min_lon, min_lat, max_lon, max_lat = bounds
        return min_lon - EPSILON <= lon <= max_lon + EPSILON and min_lat - EPSILON <= lat <= max_lat + EPSILON

    @staticmethod
    def _ogr_contains(geometry: Any, lon: float, lat: float) -> bool:
        try:
            if _OGR is None:
                return False
            point = _OGR.Geometry(_OGR.wkbPoint)
            point.AddPoint_2D(lon, lat)
            return bool(geometry.Intersects(point))
        except (AttributeError, TypeError, RuntimeError):
            return False

    def locate_all(self, lon: float, lat: float) -> list[str]:
        matches: list[str] = []
        for region, bounds, ogr_geometry in zip(self.regions, self._bounds, self._ogr_geometries):
            if not self._in_bounds(lon, lat, bounds):
                continue
            if ogr_geometry is not None:
                if self._ogr_contains(ogr_geometry, lon, lat):
                    matches.append(region["name"])
            elif geometry_contains(region["geometry"], lon, lat):
                matches.append(region["name"])
        return matches

    def locate(self, lon: float, lat: float) -> str | None:
        matches = self.locate_all(lon, lat)
        return matches[0] if matches else None
