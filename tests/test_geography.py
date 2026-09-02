# 原有的行政区几何包含判断、边界加载及同名区域多要素合并测试

import json

from fire_monitor.core.geography import RegionIndex, geometry_contains, load_regions_from_geojson


SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
}


def test_geometry_contains_inside_outside_and_boundary():
    assert geometry_contains(SQUARE, 4.5, 4.5)
    assert geometry_contains(SQUARE, 0, 5)  # 边界点按落入区域处理
    assert not geometry_contains(SQUARE, 12, 5)


def test_load_regions_with_name_field(tmp_path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"CITY": "甲市"}, "geometry": SQUARE},
            {
                "type": "Feature",
                "properties": {"CITY": "乙市"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]],
                },
            },
        ],
    }
    path = tmp_path / "cities.geojson"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    regions = load_regions_from_geojson(path, name_field="CITY", source="test")
    assert [item["name"] for item in regions] == ["甲市", "乙市"]
    assert RegionIndex(regions).locate(25, 5) == "乙市"


def test_single_city_can_merge_multiple_features(tmp_path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"district": "A"}, "geometry": SQUARE},
            {
                "type": "Feature",
                "properties": {"district": "B"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]],
                },
            },
        ],
    }
    path = tmp_path / "one_city.geojson"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    regions = load_regions_from_geojson(path, region_name="合并市")
    assert len(regions) == 1
    assert RegionIndex(regions).locate(25, 5) == "合并市"
