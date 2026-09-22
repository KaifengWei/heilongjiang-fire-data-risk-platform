from __future__ import annotations

import json

from fire_monitor.services.county_context_service import (
    CountyContextService,
)


def _write_counties(path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "测试区A",
                    "pac": "230102",
                    "city_name": "哈尔滨市",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [126.0, 45.0],
                        [127.0, 45.0],
                        [127.0, 46.0],
                        [126.0, 46.0],
                        [126.0, 45.0],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "name": "测试区B",
                    "pac": "230103",
                    "city_name": "哈尔滨市",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [127.0, 45.0],
                        [128.0, 45.0],
                        [128.0, 46.0],
                        [127.0, 46.0],
                        [127.0, 45.0],
                    ]],
                },
            },
        ],
    }

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_county_context_locates_point_and_filters_city(
    tmp_path,
):
    path = (
        tmp_path
        / "counties.geojson"
    )

    _write_counties(
        path
    )

    service = (
        CountyContextService(
            path
        )
    )

    assert service.available is True
    assert (
        service.locate_county(
            126.5,
            45.5,
        )
        == "测试区A"
    )

    collection = (
        service
        .feature_collection_for_city(
            "哈尔滨市"
        )
    )

    assert (
        len(
            collection["features"]
        )
        == 2
    )


def test_county_context_is_optional_when_file_missing(
    tmp_path,
):
    service = (
        CountyContextService(
            tmp_path
            / "missing.geojson"
        )
    )

    assert service.available is False
    assert (
        service.locate_county(
            126.5,
            45.5,
        )
        is None
    )
