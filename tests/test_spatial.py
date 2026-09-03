import json

from fire_monitor.services.spatial_service import SpatialService
from fire_monitor.storage.database import Database


def test_point_locates_region(tmp_path):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    database.upsert_regions(
        [
            {
                "name": "测试区域",
                "level": "city",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [126,45],
                            [127,45],
                            [127,46],
                            [126,46],
                            [126,45],
                        ]
                    ],
                },
                "source": "test",
                "version": "1.0",
            }
        ]
    )

    service = SpatialService(
        database
    )

    name = service.locate_region(
        longitude=126.5,
        latitude=45.5,
    )

    assert name == "测试区域"


def test_point_outside_region(tmp_path):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    database.upsert_regions(
        [
            {
                "name": "测试区域",
                "level": "city",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [126,45],
                            [127,45],
                            [127,46],
                            [126,46],
                            [126,45],
                        ]
                    ],
                },
                "source": "test",
                "version": "1.0",
            }
        ]
    )

    service = SpatialService(
        database
    )

    name = service.locate_region(
        longitude=130,
        latitude=50,
    )

    assert name is None