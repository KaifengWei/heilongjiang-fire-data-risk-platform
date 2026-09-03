# Day6-2：默认行政区数据启动初始化测试
from pathlib import Path
import json


from fire_monitor.storage.database import Database
from fire_monitor.services.region_service import RegionService
from fire_monitor.services.startup_service import StartupService



def create_geojson(
    path: Path,
):
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "默认区域"
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
                    ],
                },
            }
        ],
    }


    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )



def create_service(
    tmp_path,
):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    region_service = (
        RegionService(
            database
        )
    )

    return (
        database,
        StartupService(
            database,
            region_service,
            tmp_path
            /
            "default.geojson",
        ),
    )



def test_startup_imports_default_regions(
    tmp_path,
):

    database, startup = (
        create_service(
            tmp_path
        )
    )

    create_geojson(
        tmp_path
        /
        "default.geojson"
    )


    count = (
        startup
        .initialize_default_regions()
    )


    assert count == 1


    regions = (
        database.list_regions()
    )

    assert len(regions) == 1



def test_startup_skips_existing_regions(
    tmp_path,
):

    database, startup = (
        create_service(
            tmp_path
        )
    )

    create_geojson(
        tmp_path
        /
        "default.geojson"
    )


    startup.initialize_default_regions()


    count = (
        startup
        .initialize_default_regions()
    )


    assert count == 0


def test_startup_without_file_does_not_fail(
    tmp_path,
):

    database, startup = (
        create_service(
            tmp_path
        )
    )


    count = (
        startup
        .initialize_default_regions()
    )


    assert count == 0