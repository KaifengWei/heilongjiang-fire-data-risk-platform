# Day6-3：黑龙江行政区基础数据完整性测试
from pathlib import Path

import json


def test_heilongjiang_city_geojson_structure():

    path = (
        Path("data")
        /
        "regions"
        /
        "heilongjiang_city.geojson"
    )

    assert path.exists()


    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


    assert (
        data["type"]
        ==
        "FeatureCollection"
    )


    features = (
        data["features"]
    )

    assert len(features) == 13



def test_region_names_exist():

    path = (
        Path("data")
        /
        "regions"
        /
        "heilongjiang_city.geojson"
    )

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    names = []

    for feature in data["features"]:

        name = (
            feature
            .get("properties", {})
            .get("name")
        )

        assert name

        names.append(name)


    assert (
        "哈尔滨市"
        in names
    )

    assert (
        "大兴安岭地区"
        in names
    )