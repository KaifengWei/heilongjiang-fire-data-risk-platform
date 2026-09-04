from fire_monitor.storage.database import Database
from fire_monitor.services.statistics_service import StatisticsService
import pytest

def test_region_statistics(tmp_path):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()


    run_id = database.start_import(
        "test",
        "test",
    )


    database.insert_active_fire_rows(
        [
            {
                "dedupe_key": "fire1",
                "acquired_date": "2026-03-15",
                "latitude": 45.8,
                "longitude": 126.5,
                "region_name": "哈尔滨市",
                "firms_source": "VIIRS",
            },
            {
                "dedupe_key": "fire2",
                "acquired_date": "2026-03-15",
                "latitude": 46.0,
                "longitude": 123.9,
                "region_name": "齐齐哈尔市",
                "firms_source": "VIIRS",
            },
        ],
        run_id,
    )


    database.insert_burned_pixel_rows(
        [
            {
                "dedupe_key": "pixel1",
                "burned_date": "2026-03-15",
                "latitude": 45.8,
                "longitude": 126.5,
                "region_name": "哈尔滨市",
                "cell_area_km2": 0.25,
                "source_product": "MCD64A1",
            },
            {
                "dedupe_key": "pixel2",
                "burned_date": "2026-03-15",
                "latitude": 45.9,
                "longitude": 126.6,
                "region_name": "哈尔滨市",
                "cell_area_km2": 0.25,
                "source_product": "MCD64A1",
            },
        ],
        run_id,
    )


    service = StatisticsService(
        database
    )


    result = service.region_statistics()


    harbin = next(
        x for x in result
        if x["region_name"] == "哈尔滨市"
    )


    assert harbin["active_fire_count"] == 1
    assert harbin["burned_pixel_count"] == 2
    assert harbin["burned_area_km2"] == 0.5



def test_region_ranking(tmp_path):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    service = StatisticsService(
        database
    )

    assert service.region_ranking() == []

    def test_empty_region_statistics(tmp_path):
        database = Database(
            tmp_path / "test.sqlite"
        )

        database.initialize()

        service = StatisticsService(
            database
        )

        result = (
            service.region_statistics()
        )

        assert result == []

def test_region_ranking_order(tmp_path):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    run_id = database.start_import(
        "test",
        "test",
    )


    database.insert_burned_pixel_rows(
        [
            {
                "dedupe_key": "a",
                "burned_date": "2026-03-15",
                "latitude": 45,
                "longitude": 126,
                "region_name": "哈尔滨市",
                "cell_area_km2": 1,
                "source_product": "MCD64A1",
            },
            {
                "dedupe_key": "b",
                "burned_date": "2026-03-15",
                "latitude": 46,
                "longitude": 127,
                "region_name": "绥化市",
                "cell_area_km2": 3,
                "source_product": "MCD64A1",
            },
        ],
        run_id,
    )


    service = StatisticsService(
        database
    )


    result = service.region_ranking()


    assert (
        result[0]["region_name"]
        ==
        "绥化市"
    )

def test_invalid_ranking_metric(tmp_path):

    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    service = StatisticsService(
        database
    )


    with pytest.raises(
        ValueError
    ):
        service.region_ranking(
            metric="wrong"
        )