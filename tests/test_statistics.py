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

def test_task_region_statistics_are_isolated(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )
    database.initialize()

    for task_id in (
        "TASK-A",
        "TASK-B",
    ):
        database.create_analysis_task(
            task_id=task_id,
            name=task_id,
            software_version="test",
        )

    fire_run_a = database.start_import(
        "active_fire_observations",
        "fire-a",
        task_id="TASK-A",
    )
    fire_run_b = database.start_import(
        "active_fire_observations",
        "fire-b",
        task_id="TASK-B",
    )

    burned_run_a = database.start_import(
        "burned_pixels_tif",
        "burned-a",
        task_id="TASK-A",
    )
    burned_run_b = database.start_import(
        "burned_pixels_tif",
        "burned-b",
        task_id="TASK-B",
    )

    database.insert_active_fire_rows(
        [
            {
                "dedupe_key": "fire-a",
                "acquired_date": "2026-03-15",
                "latitude": 45.8,
                "longitude": 126.5,
                "region_name": "哈尔滨市",
                "firms_source": "VIIRS",
            },
        ],
        fire_run_a,
    )

    database.insert_active_fire_rows(
        [
            {
                "dedupe_key": "fire-b",
                "acquired_date": "2026-03-15",
                "latitude": 47.3,
                "longitude": 123.9,
                "region_name": "齐齐哈尔市",
                "firms_source": "VIIRS",
            },
        ],
        fire_run_b,
    )

    database.insert_burned_pixel_rows(
        [
            {
                "dedupe_key": "pixel-a",
                "burned_date": "2026-03-15",
                "latitude": 45.8,
                "longitude": 126.5,
                "region_name": "哈尔滨市",
                "cell_area_km2": 0.25,
                "source_product": "MCD64A1",
            },
        ],
        burned_run_a,
    )

    database.insert_burned_pixel_rows(
        [
            {
                "dedupe_key": "pixel-b",
                "burned_date": "2026-03-15",
                "latitude": 47.3,
                "longitude": 123.9,
                "region_name": "齐齐哈尔市",
                "cell_area_km2": 0.5,
                "source_product": "MCD64A1",
            },
        ],
        burned_run_b,
    )

    with database.connect() as conn:
        fire_a_id = conn.execute(
            """
            SELECT id
            FROM active_fire_observations
            WHERE dedupe_key = 'fire-a'
            """
        ).fetchone()["id"]

        fire_b_id = conn.execute(
            """
            SELECT id
            FROM active_fire_observations
            WHERE dedupe_key = 'fire-b'
            """
        ).fetchone()["id"]

        pixel_a_id = conn.execute(
            """
            SELECT id
            FROM burned_pixels
            WHERE dedupe_key = 'pixel-a'
            """
        ).fetchone()["id"]

        pixel_b_id = conn.execute(
            """
            SELECT id
            FROM burned_pixels
            WHERE dedupe_key = 'pixel-b'
            """
        ).fetchone()["id"]

        conn.execute(
            """
            INSERT INTO
            active_fire_observation_sources(
                observation_id,
                source_record_key,
                firms_source,
                processing_class,
                import_run_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fire_a_id,
                "source-a",
                "VIIRS",
                "SP",
                fire_run_a,
                "2026-03-15T00:00:00+00:00",
            ),
        )

        conn.execute(
            """
            INSERT INTO
            active_fire_observation_sources(
                observation_id,
                source_record_key,
                firms_source,
                processing_class,
                import_run_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fire_b_id,
                "source-b",
                "VIIRS",
                "SP",
                fire_run_b,
                "2026-03-15T00:00:00+00:00",
            ),
        )

        conn.execute(
            """
            INSERT INTO burned_pixel_run_membership(
                run_id,
                burned_pixel_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                burned_run_a,
                pixel_a_id,
                "2026-03-15T00:00:00+00:00",
            ),
        )

        conn.execute(
            """
            INSERT INTO burned_pixel_run_membership(
                run_id,
                burned_pixel_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                burned_run_b,
                pixel_b_id,
                "2026-03-15T00:00:00+00:00",
            ),
        )

    for run_id in (
        fire_run_a,
        fire_run_b,
        burned_run_a,
        burned_run_b,
    ):
        database.finish_import(
            run_id,
            input_count=1,
            stored_count=1,
        )

    service = StatisticsService(
        database
    )

    result_a = (
        service.task_region_statistics(
            "TASK-A"
        )
    )

    result_b = (
        service.task_region_statistics(
            "TASK-B"
        )
    )

    assert result_a == [
        {
            "region_name": "哈尔滨市",
            "active_fire_count": 1,
            "burned_pixel_count": 1,
            "burned_area_km2": 0.25,
        }
    ]

    assert result_b == [
        {
            "region_name": "齐齐哈尔市",
            "active_fire_count": 1,
            "burned_pixel_count": 1,
            "burned_area_km2": 0.5,
        }
    ]