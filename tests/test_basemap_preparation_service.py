"""Geo-referenced official-style tile conversion, never generated as a fake map."""

import json

import pytest
from osgeo import ogr, osr

from fire_monitor.services.basemap_preparation_service import (
    discover_sources, inspect_source, prepare_outline, write_geojson_atomic,
)
from fire_monitor.services.reference_basemap_service import ReferenceBasemapStore


def _tile(path, polygons, *, srs=True, layer_name="BOUA"):
    driver = ogr.GetDriverByName("GPKG")
    assert driver is not None
    ds = driver.CreateDataSource(str(path))
    spatial = osr.SpatialReference()
    spatial.ImportFromEPSG(4490)
    layer = ds.CreateLayer(layer_name, srs=spatial if srs else None, geom_type=ogr.wkbPolygon)
    for ring in polygons:
        coords = ", ".join(f"{lon} {lat}" for lon, lat in ring)
        geom = ogr.CreateGeometryFromWkt(f"POLYGON (({coords}))")
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(geom)
        assert layer.CreateFeature(feature) == 0
        feature = None
    ds = None


RECT_A = [(110,30),(111,30),(111,31),(110,31),(110,30)]
RECT_B = [(111,30),(112,30),(112,31),(111,31),(111,30)]


def test_merge_two_official_style_sheets_and_install(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _tile(root / "A.gpkg", [RECT_A])
    _tile(root / "B.gpkg", [RECT_B])
    sources = discover_sources(root)
    assert len(sources) == 2
    assert inspect_source(sources[0])[0]["name"] == "BOUA"
    result = prepare_outline(sources, expected_sources=2)
    assert result.source_files == 2
    assert result.files_with_polygons == 2
    assert result.input_polygons == 2
    assert result.bounds == (110, 30, 112, 31)
    obj = json.loads(result.geojson)
    assert len(obj["features"]) == 1
    assert obj["features"][0]["geometry"]["type"] == "Polygon"
    outfile = tmp_path / "combined.geojson"
    assert write_geojson_atomic(outfile, result.geojson).read_bytes() == result.geojson

    store = ReferenceBasemapStore(tmp_path)
    result_saved = store.install(result.geojson, source="真实测试来源", authorized=True)
    assert result_saved["feature_count"] == 1
    assert len(store.context([110,30,112,31])["features"]) == 1
    assert store.context([90, 20, 91, 21])["features"] == []


def test_reject_incomplete_sheets_missing_srs_and_unknown_layer(tmp_path):
    path = tmp_path / "sheet.gpkg"
    _tile(path, [RECT_A])
    with pytest.raises(ValueError, match="图幅数量不符"):
        prepare_outline([path], expected_sources=77)
    with pytest.raises(ValueError, match="缺少"):
        prepare_outline([path], layer_name="NOT_A_LAYER")
    no_srs = tmp_path / "nosrs.gpkg"
    _tile(no_srs, [RECT_B], srs=False)
    with pytest.raises(ValueError, match="缺少坐标参考系"):
        prepare_outline([no_srs])
    assert prepare_outline([no_srs], source_epsg=4490).input_polygons == 1


def test_skip_no_boundary_layer_only_if_requested(tmp_path):
    first = tmp_path / "empty.gpkg"
    second = tmp_path / "boundary.gpkg"
    _tile(first, [RECT_A], layer_name="HYDA")
    _tile(second, [RECT_B], layer_name="BOUA")
    result = prepare_outline(
        [first, second], expected_sources=2, allow_missing_layer=True,
    )
    assert result.input_polygons == 1
    assert len(result.empty_files) == 1
    assert "empty.gpkg" in result.empty_files[0]


def test_discovery_does_not_descend_geodatabase_folders(tmp_path):
    root = tmp_path / "official"
    root.mkdir()
    geodatabase = root / "H49.gdb"
    geodatabase.mkdir()
    (geodatabase / "BOUA.json").write_text("not a GeoJSON", encoding="utf-8")
    _tile(root / "A.gpkg", [RECT_A])
    assert {x.name for x in discover_sources(root)} == {"H49.gdb", "A.gpkg"}
    assert discover_sources(root / "A.gpkg") == [root / "A.gpkg"]
    (root / "pack.zip").write_bytes(b"dummy")
    with pytest.raises(ValueError, match="已解压"):
        discover_sources(root / "pack.zip")


def test_map_canvas_scales_without_argument_spreading():
    # Code regression for large national outlines; runtime geometry is
    # still sourced exclusively from properly installed geodata.
    from pathlib import Path
    js_path = Path(__file__).resolve().parents[1] / "static" / "product.js"
    source = js_path.read_text(encoding="utf-8")
    body = source[source.index("async function initTaskMapWorkspace()"):]
    assert "function pointsBounds(coords)" in body
    assert "Math.min(...xs)" not in body
    assert "Math.max(...localXs)" not in body
    assert "ctx.fill('evenodd')" in body
    assert "reference_layer === 'basemap'" in body
