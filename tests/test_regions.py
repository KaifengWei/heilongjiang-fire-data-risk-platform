# Day6：行政区基础数据导入与管理测试
from pathlib import Path
import json

from fire_monitor.storage.database import Database
from fire_monitor.services.region_service import RegionService



def create_geojson(
    path: Path
):

    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "测试区域"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [
                                126,
                                45
                            ],
                            [
                                126.1,
                                45
                            ],
                            [
                                126.1,
                                45.1
                            ],
                            [
                                126,
                                45.1
                            ],
                            [
                                126,
                                45
                            ],
                        ]
                    ]
                }
            }
        ]
    }


    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )



def test_import_regions_from_geojson(
    tmp_path,
):

    database = Database(
        tmp_path / "test.sqlite"
    )
    database.initialize()
    
    service = RegionService(
        database
    )


    geojson = (
        tmp_path
        /
        "region.geojson"
    )

    create_geojson(
        geojson
    )


    count = service.import_geojson(
        geojson,
        source="test",
        version="1.0",
    )


    assert count == 1


    regions = (
        service.list_regions()
    )


    assert len(regions) == 1

    assert (
        regions[0]["name"]
        ==
        "测试区域"
    )