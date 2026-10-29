from io import BytesIO
import json
import pytest
from fire_monitor.services.region_preview_service import RegionPreviewService, load_geojson_boundaries


def _region(name, minx, miny, maxx, maxy):
    return {"name": name, "level": "city", "geometry": {
        "type": "Polygon", "coordinates": [[
            [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]
        ]]}}


def test_detects_two_regions_and_unmatched_without_guessing():
    service = RegionPreviewService([_region("甲市", 110, 30, 111, 31), _region("乙市", 112, 32, 113, 33)])
    csv_data = ("latitude,longitude,acq_date\n30.5,110.5,2026-01-01\n32.5,112.5,2026-01-01\n"
                "32.7,112.6,2026-01-02\n40.0,118.0,2026-01-02\nbad,110,2026-01-02\n").encode()
    r = service.preview([("firms.csv", BytesIO(csv_data))])
    assert r["input_rows"] == 5
    assert r["valid_coordinate_rows"] == 4
    assert r["invalid_coordinate_rows"] == 1
    assert r["matched_rows"] == 3
    assert r["unmatched_rows"] == 1
    assert [(x["name"], x["observations"]) for x in r["candidates"]] == [("乙市", 2), ("甲市", 1)]
    assert "selected_region" not in r


def test_empty_boundaries_cannot_claim_national_coverage():
    r = RegionPreviewService([]).preview([("s.csv", BytesIO(b"latitude,longitude\n31,114\n"))])
    assert r["matched_rows"] == 0
    assert r["unmatched_rows"] == 1
    assert r["candidates"] == []
    assert "GeoJSON" in r["message"]


def test_geojson_upload_rejects_invalid_shape_and_crs():
    payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "示例区"}, "geometry": _region("s", 110, 30, 111, 31)["geometry"]}]}
    result = load_geojson_boundaries(json.dumps(payload).encode())
    assert len(result) == 1
    assert RegionPreviewService(result).preview([("s.csv", BytesIO(b"latitude,longitude\n30.5,110.5\n"))])["matched_rows"] == 1
    payload["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(ValueError, match="EPSG:4326"):
        load_geojson_boundaries(json.dumps(payload).encode())


def test_invalid_csv_missing_coordinates():
    with pytest.raises(ValueError, match="经纬度"):
        RegionPreviewService([]).preview([("s.csv", BytesIO(b"acq_date,frp\n2026-01-01,2\n"))])

def test_preview_includes_simplified_region_outline():
    service = RegionPreviewService([_region("示例市", 110, 30, 111, 31)])
    data = service.preview([("firms.csv", BytesIO(b"latitude,longitude\\n30.5,110.5\\n"))])
    assert data["candidates"][0]["id"] == 0
    assert data["sampled_points"] == [[110.5, 30.5]]
    assert data["preview_shapes"]["features"][0]["geometry"]["type"] == "Polygon"
