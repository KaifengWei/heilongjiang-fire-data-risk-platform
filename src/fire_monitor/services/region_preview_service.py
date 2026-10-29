"""Preview FIRMS spatial coverage against available analysis boundaries.

This module does not imply nationwide boundary coverage and does not change
stored regions or task data. Scope confirmation belongs to the next stage.
"""
from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter
from typing import Any, BinaryIO, Iterable

from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree

MAX_CSV_BYTES = 32 * 1024 * 1024
MAX_BOUNDARY_BYTES = 16 * 1024 * 1024
MAX_OBSERVATIONS = 250_000


def _decode(data: bytes, label: str) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{label} 文件编码无法识别，请使用 UTF-8 CSV/GeoJSON。")


def load_geojson_boundaries(data: bytes) -> list[dict[str, Any]]:
    if not data or len(data) > MAX_BOUNDARY_BYTES:
        raise ValueError("边界文件为空或超过 16 MB 上限。")
    try:
        payload = json.loads(_decode(data, "GeoJSON"))
    except json.JSONDecodeError as exc:
        raise ValueError("边界文件不是有效的 GeoJSON。") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("边界文件必须是 GeoJSON FeatureCollection。")
    crs = payload.get("crs")
    if crs:
        value = str((crs.get("properties") or {}).get("name", "")).upper()
        if value not in ("EPSG:4326", "URN:OGC:DEF:CRS:OGC:1.3:CRS84", "OGC:CRS84"):
            raise ValueError("边界文件必须采用 WGS84 经纬度坐标（EPSG:4326）。")
    result = []
    for index, feature in enumerate(payload.get("features", []), start=1):
        if not isinstance(feature, dict):
            raise ValueError("GeoJSON 包含无效 Feature。")
        props = feature.get("properties") or {}
        name = str(props.get("name") or props.get("NAME") or props.get("name_zh") or "").strip()
        if not name:
            raise ValueError(f"第 {index} 个区域缺少 name 字段。")
        geometry = feature.get("geometry")
        try:
            polygon = shape(geometry)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"区域 {name} 的几何数据无效。") from exc
        if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid:
            raise ValueError(f"区域 {name} 必须是有效的多边形。")
        xmin, ymin, xmax, ymax = polygon.bounds
        if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
            raise ValueError(f"区域 {name} 的坐标超出经纬度范围。")
        result.append({"name": name, "level": str(props.get("level") or "custom"),
                       "geometry": geometry, "source": "uploaded"})
    if not result:
        raise ValueError("GeoJSON 没有可用区域。")
    if len(result) > 4000:
        raise ValueError("GeoJSON 区域数量超过 4000 个。")
    return result


class RegionPreviewService:
    def __init__(self, regions: Iterable[dict[str, Any]]):
        self.regions = []
        geometries = []
        for row in regions:
            geometry = row.get("geometry")
            if isinstance(geometry, str):
                geometry = json.loads(geometry)
            polygon = shape(geometry)
            if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid:
                raise ValueError("区域边界存在无效多边形。")
            geometries.append(polygon)
            self.regions.append({"name": str(row["name"]), "level": str(row.get("level") or "custom")})
        self._tree = STRtree(geometries) if geometries else None
        self._geometries = geometries

    def preview(self, uploads: Iterable[tuple[str, BinaryIO]]) -> dict[str, Any]:
        counts: Counter[int] = Counter()
        raw_rows = valid_rows = invalid_rows = matched_rows = 0
        filenames = []
        sampled_points: list[list[float]] = []
        for filename, stream in uploads:
            if not filename.lower().endswith(".csv"):
                raise ValueError("只接收 FIRMS CSV 数据文件。")
            data = stream.read(MAX_CSV_BYTES + 1)
            if not data or len(data) > MAX_CSV_BYTES:
                raise ValueError("CSV 文件为空或超过单文件 32 MB 限制。")
            filenames.append(filename)
            reader = csv.DictReader(io.StringIO(_decode(data, filename)))
            fields = {str(field).strip().lower(): field for field in (reader.fieldnames or [])}
            lat_col = fields.get("latitude") or fields.get("lat")
            lon_col = fields.get("longitude") or fields.get("lon") or fields.get("lng")
            if not lat_col or not lon_col:
                raise ValueError(f"{filename} 缺少 latitude/longitude 经纬度列。")
            for row in reader:
                raw_rows += 1
                if raw_rows > MAX_OBSERVATIONS:
                    raise ValueError("一次预览最多读取 250000 条记录，请缩小数据范围。")
                try:
                    lat, lon = float(row[lat_col]), float(row[lon_col])
                except (ValueError, TypeError, KeyError):
                    invalid_rows += 1
                    continue
                if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
                    invalid_rows += 1
                    continue
                valid_rows += 1
                if len(sampled_points) < 500:
                    sampled_points.append([round(lon, 5), round(lat, 5)])
                indexes = [] if self._tree is None else self._tree.query(
                    Point(lon, lat), predicate="intersects")
                if len(indexes):
                    matched_rows += 1
                for index in indexes:
                    counts[int(index)] += 1
        if not filenames:
            raise ValueError("请选择 FIRMS CSV 文件。")
        candidates = [
            {"id": i, "name": row["name"], "level": row["level"], "observations": counts[i],
             "share_of_valid": round(100 * counts[i] / valid_rows, 2) if valid_rows else 0.0}
            for i, row in enumerate(self.regions) if counts[i] > 0
        ]
        candidates.sort(key=lambda item: (-item["observations"], item["name"]))
        outline_features = []
        for candidate in candidates[:12]:
            polygon = self._geometries[candidate["id"]]
            compact = mapping(polygon.simplify(0.03, preserve_topology=True))
            if len(json.dumps(compact)) > 100_000:
                compact = mapping(polygon.simplify(0.15, preserve_topology=True))
            if len(json.dumps(compact)) <= 100_000:
                outline_features.append({
                    "type": "Feature",
                    "properties": {"id": candidate["id"], "name": candidate["name"]},
                    "geometry": compact,
                })
        return {
            "files": filenames,
            "input_rows": raw_rows,
            "valid_coordinate_rows": valid_rows,
            "invalid_coordinate_rows": invalid_rows,
            "matched_rows": matched_rows,
            "unmatched_rows": valid_rows - matched_rows,
            "boundary_scope": "available_boundaries_only",
            "sampled_points": sampled_points,
            "preview_shapes": {"type": "FeatureCollection", "features": outline_features},
            "candidates": candidates,
            "message": (
                "已根据当前可用的行政区边界识别候选区域，请核对后确定分析范围。"
                if candidates else
                "当前边界数据无法覆盖这些观测点，请导入相应的 GeoJSON 边界。"
            ),
        }
