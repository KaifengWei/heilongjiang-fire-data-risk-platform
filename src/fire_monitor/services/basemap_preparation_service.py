"""Prepare a lightweight WGS84 offline outline from licensed GIS source files.

Handles unzipped official 1:1M BOUA layers in GDB, Shapefile and GeoPackage.
This tool NEVER downloads or bundles a purported national map. The operator
supplies actual source files, verifies their coverage and confirms rights.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from osgeo import ogr, osr
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


SUPPORTED_SUFFIXES = {".shp", ".gpkg", ".geojson", ".json"}
DEFAULT_LAYER = "BOUA"
MAX_GEOMETRIES = 300_000


@dataclass
class PreparationResult:
    geojson: bytes
    source_files: int
    files_with_polygons: int
    input_polygons: int
    empty_files: tuple[str, ...]
    bounds: tuple[float, float, float, float]
    output_bytes: int


def discover_sources(root: str | Path, *, exclude: str | Path | None = None) -> list[Path]:
    """Find vector datasets without descending into FileGDB directories."""
    root = Path(root).resolve()
    excluded = Path(exclude).resolve() if exclude else None
    if not root.exists():
        raise ValueError(f"输入路径不存在：{root}")
    if root.is_file():
        if root.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("请输入已解压的 .gdb 目录或 SHP/GPKG/GeoJSON 数据文件。")
        return [] if root == excluded else [root]
    if root.suffix.lower() == ".gdb":
        return [root]
    found: list[Path] = []
    for directory, names, filenames in os.walk(root):
        folder = Path(directory)
        for name in list(names):
            if name.lower().endswith(".gdb"):
                candidate = folder / name
                if candidate.resolve() != excluded:
                    found.append(candidate)
                names.remove(name)
        for name in filenames:
            candidate = folder / name
            if candidate.suffix.lower() in SUPPORTED_SUFFIXES and candidate.resolve() != excluded:
                found.append(candidate)
    return sorted(found, key=lambda p: str(p).casefold())


def inspect_source(path: str | Path) -> list[dict]:
    ds = ogr.Open(str(path), 0)
    if ds is None:
        raise ValueError(f"GDAL 无法打开地图数据：{path}")
    layers = []
    for layer in ds:
        srs = layer.GetSpatialRef()
        layers.append({
            "name": layer.GetName(),
            "features": layer.GetFeatureCount(),
            "srs": srs.GetAuthorityCode(None) if srs is not None else None,
        })
    ds = None
    return layers


def _target_projection():
    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return target


def _source_projection(layer, override_epsg: int | None):
    origin = layer.GetSpatialRef()
    if origin is not None:
        origin = origin.Clone()
    elif override_epsg is not None:
        origin = osr.SpatialReference()
        if origin.ImportFromEPSG(override_epsg) != 0:
            raise ValueError(f"无效的来源 EPSG：{override_epsg}")
    else:
        raise ValueError(
            f"图层 {layer.GetName()} 缺少坐标参考系，请提供明确的 --source-epsg。"
        )
    origin.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return origin


def _only_polygons(geom, dataset_name: str, fid: int):
    if geom is None or geom.IsEmpty():
        return None
    try:
        poly = shape(json.loads(geom.ExportToJson()))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{dataset_name} 要素 {fid} 坐标无法读取。") from exc
    if poly.geom_type not in ("Polygon", "MultiPolygon") or not poly.is_valid:
        raise ValueError(f"{dataset_name} 要素 {fid} 不是有效的行政区面。")
    coords = poly.bounds
    if not all(math.isfinite(x) for x in coords):
        raise ValueError(f"{dataset_name} 要素 {fid} 包含无效坐标。")
    w, s, e, n = coords
    if not (-180 <= w <= e <= 180 and -90 <= s <= n <= 90):
        raise ValueError(f"{dataset_name} 要素 {fid} 坐标超出经纬度范围。")
    return poly


def prepare_outline(
    files: list[Path],
    *,
    layer_name: str = DEFAULT_LAYER,
    source_epsg: int | None = None,
    simplify_degrees: float = 0.01,
    allow_missing_layer: bool = False,
    expected_sources: int | None = None,
) -> PreparationResult:
    """Dissolve verified polygon layers into one geographic outline.

    The dissolve removes internal administrative splits. A single, simplified
    MultiPolygon is suitable for offline coordinate reference, not for
    identifying a point's province/county or producing a published map.
    """
    if not files:
        raise ValueError("没有找到可处理的 GIS 文件。")
    if expected_sources is not None and len(files) != expected_sources:
        raise ValueError(
            f"图幅数量不符：找到 {len(files)} 份，要求 {expected_sources} 份；"
            "请核对原始分幅文件。"
        )
    if not 0 <= simplify_degrees <= 0.06:
        raise ValueError("简化容差必须在 0 至 0.06 度之间。")

    target = _target_projection()
    per_file = []
    empty = []
    total = 0
    used = 0
    for path in files:
        ds = ogr.Open(str(path), 0)
        if ds is None:
            raise ValueError(f"GDAL 无法打开：{path}")
        layer = next((ds.GetLayerByIndex(i) for i in range(ds.GetLayerCount())
                      if ds.GetLayerByIndex(i).GetName().casefold() == layer_name.casefold()), None)
        if layer is None and layer_name.lower() == "auto" and ds.GetLayerCount() == 1:
            layer = ds.GetLayerByIndex(0)
        if layer is None:
            ds = None
            if allow_missing_layer:
                empty.append(str(path))
                continue
            raise ValueError(f"{path} 缺少 {layer_name} 图层；请检查原始分幅数据。")

        origin = _source_projection(layer, source_epsg)
        transform = osr.CoordinateTransformation(origin, target)
        batch = []
        tile_unions = []
        for feature in layer:
            fid = feature.GetFID()
            geometry = feature.GetGeometryRef()
            if geometry is None or geometry.IsEmpty():
                continue
            owned = geometry.Clone()
            try:
                if owned.Transform(transform) != 0:
                    raise ValueError(f"{path} 要素 {fid} 坐标变换失败。")
            except RuntimeError as exc:
                raise ValueError(f"{path} 要素 {fid} 坐标变换失败。") from exc
            poly = _only_polygons(owned, str(path), fid)
            if poly is None:
                continue
            batch.append(poly)
            total += 1
            if total > MAX_GEOMETRIES:
                raise ValueError("行政区面数量超过安全限制，请先按需筛选图层。")
            if len(batch) >= 128:
                tile_unions.append(unary_union(batch))
                batch.clear()
        if batch:
            tile_unions.append(unary_union(batch))
        if tile_unions:
            per_file.append(unary_union(tile_unions))
            used += 1
        else:
            empty.append(str(path))
        ds = None

    if not per_file:
        raise ValueError("所选数据未包含有效行政区面，无法生成地图。")

    outline = unary_union(per_file)
    if outline.is_empty or outline.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("行政区面合并失败。")
    outline = outline.simplify(simplify_degrees, preserve_topology=True)
    if not outline.is_valid:
        raise ValueError("轮廓简化后几何无效；请降低简化容差。")
    geom = mapping(outline)
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "实际来源数据轮廓"},
            "geometry": geom,
        }],
    }
    raw = json.dumps(
        collection, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return PreparationResult(
        geojson=raw,
        source_files=len(files),
        files_with_polygons=used,
        input_polygons=total,
        empty_files=tuple(empty),
        bounds=tuple(float(x) for x in outline.bounds),
        output_bytes=len(raw),
    )


def write_geojson_atomic(output: str | Path, data: bytes) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix="basemap-",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output
