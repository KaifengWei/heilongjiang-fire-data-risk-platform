"""Optional user-installed WGS84 reference map for offline FIRMS visualization.

The reference layer changes only the Canvas background. It never changes
FIRMS observations, the area filter, stored region assignments or reports.
The distributable deliberately does not bundle an unverified national map.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.errors import GEOSException
from shapely.geometry import mapping, shape

from fire_monitor.services.map_context_service import build_observation_boundary_context

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_FEATURES = 350


class ReferenceBasemapStore:
    def __init__(self, storage_dir: str | Path):
        self.path = Path(storage_dir) / "map_background" / "reference_basemap.json"

    def load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        if not isinstance(saved, dict):
            return None
        if not isinstance(saved.get("features"), list):
            return None
        if not isinstance(saved.get("metadata"), dict):
            return None
        return saved

    def summary(self) -> dict[str, Any]:
        saved = self.load()
        if saved is None:
            return {"installed": False, "source": "", "feature_count": 0}
        meta = saved["metadata"]
        return {
            "installed": True,
            "source": str(meta.get("source") or ""),
            "feature_count": len(saved["features"]),
            "sha256": str(meta.get("sha256") or ""),
        }

    def context(self, observed_bbox: list[float] | None) -> dict[str, Any]:
        """Map features intersecting the observation extent (legacy local view)."""
        saved = self.load()
        if saved is None:
            return {"type": "FeatureCollection", "features": []}
        return build_observation_boundary_context(
            saved["features"], observed_bbox, limit=100,
        )

    def full_context(self) -> dict[str, Any]:
        """All installed map features for a true full-outline view.

        Imports are already validated and size-limited on installation.
        No fake national extent is synthesized for partial datasets.
        """
        saved = self.load()
        return {
            "type": "FeatureCollection",
            "features": list(saved["features"]) if saved is not None else [],
        }

    def install(self, raw: bytes, *, source: str, authorized: bool) -> dict[str, Any]:
        source = str(source or "").strip()
        if not authorized:
            raise ValueError("请确认已获准使用该地图数据。")
        if not 1 <= len(source) <= 250:
            raise ValueError("请填写 1 至 250 字的地图数据来源。")
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError("GeoJSON 文件为空或大于 12 MB，请先简化地图轮廓。")
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("无法读取 GeoJSON，请使用 UTF-8 编码。") from exc
        if not isinstance(payload, dict):
            raise ValueError("GeoJSON 格式不正确。")
        crs = payload.get("crs")
        if crs is not None:
            crs_value = json.dumps(crs, ensure_ascii=False).upper()
            if "4326" not in crs_value and "CRS84" not in crs_value:
                raise ValueError("请将地图数据转换为 WGS84 经纬度坐标。")
        if payload.get("type") == "FeatureCollection":
            originals = payload.get("features")
        elif payload.get("type") == "Feature":
            originals = [payload]
        elif payload.get("type") in ("Polygon", "MultiPolygon"):
            originals = [{"type": "Feature", "geometry": payload, "properties": {}}]
        else:
            originals = None
        if not isinstance(originals, list) or not 1 <= len(originals) <= MAX_FEATURES:
            raise ValueError("需要包含 1 至 350 个面要素的 GeoJSON。")

        processed = []
        for index, feature in enumerate(originals):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError("地图仅支持面要素，不支持点、线或混合几何。")
            try:
                geometry = shape(feature["geometry"])
            except (KeyError, ValueError, TypeError, GEOSException) as exc:
                raise ValueError(f"第 {index + 1} 个地图面无法读取。") from exc
            if (geometry.is_empty or not geometry.is_valid
                    or geometry.geom_type not in ("Polygon", "MultiPolygon")):
                raise ValueError(f"第 {index + 1} 个要素不是有效的区域轮廓。")
            west, south, east, north = geometry.bounds
            if (not all(math.isfinite(x) for x in (west, south, east, north))
                    or not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90)):
                raise ValueError("地图坐标不在合理的经纬度范围，请核对坐标系。")
            props = feature.get("properties") or {}
            if not isinstance(props, dict):
                props = {}
            # geoBoundaries uses shapeName; never fabricate a province name
            # from its position in a GeoJSON file.
            raw_name = next(
                (props[key] for key in (
                    "shapeName", "name", "NAME", "NAME_1", "name_zh",
                    "NAME_CHN", "province_name", "province", "Name"
                ) if isinstance(props.get(key), str) and props[key].strip()),
                "",
            )
            name = str(raw_name).strip()[:90]
            label_point = geometry.representative_point()
            simplified = geometry.simplify(0.003, preserve_topology=True)
            processed.append({
                "type": "Feature",
                "properties": {
                    "name": name,
                    "source": source,
                    "reference_only": True,
                    "reference_layer": "basemap",
                    "label_point": [label_point.x, label_point.y],
                },
                "geometry": mapping(simplified),
            })

        metadata = {
            "source": source,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "feature_count": len(processed),
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "coordinate_system": "EPSG:4326",
        }
        encoded = json.dumps(
            {"type": "FeatureCollection", "features": processed, "metadata": metadata},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_OUTPUT_BYTES:
            raise ValueError("底图处理后仍然过大，请进一步简化几何。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix="map-", suffix=".tmp",
                dir=self.path.parent, delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return self.summary()
