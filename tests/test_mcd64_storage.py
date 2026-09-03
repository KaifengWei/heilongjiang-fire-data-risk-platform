# Day5C-1：MCD64A1烧毁像元规范身份、数据库去重及运行关系测试

import sqlite3

from fire_monitor.core.mcd64 import (
    canonical_burned_pixel_key,
)
from fire_monitor.storage.database import (
    Database,
)
from fire_monitor.storage.mcd64_repository import (
    Mcd64Repository,
)


def _base_row(
    *,
    dedupe_key: str,
):
    canonical_key = (
        canonical_burned_pixel_key(
            source_product="MCD64A1",
            burned_date="2026-03-15",
            longitude=126.65,
            latitude=45.75,
            cell_area_km2=0.247,
        )
    )

    return {
        "dedupe_key": dedupe_key,
        "canonical_key": (
            canonical_key
        ),
        "burned_date": (
            "2026-03-15"
        ),
        "doy": 74,
        "latitude": 45.75,
        "longitude": 126.65,
        "region_name": "测试区域",
        "cell_area_km2": 0.247,
        "source_product": "MCD64A1",
        "raster_name": "test.tif",
        "qa_value": 3,
    }


def test_canonical_key_does_not_depend_on_raster_file():
    first = (
        canonical_burned_pixel_key(
            source_product="MCD64A1",
            burned_date="2026-03-15",
            longitude=126.65,
            latitude=45.75,
            cell_area_km2=0.247,
        )
    )

    second = (
        canonical_burned_pixel_key(
            source_product="MCD64A1",
            burned_date="2026-03-15",
            longitude=126.65,
            latitude=45.75,
            cell_area_km2=0.247,
        )
    )

    assert first == second

    different_grid = (
        canonical_burned_pixel_key(
            source_product="MCD64A1",
            burned_date="2026-03-15",
            longitude=126.65,
            latitude=45.75,
            cell_area_km2=1.0,
        )
    )

    assert (
        different_grid
        != first
    )


def test_same_pixel_from_two_runs_is_stored_once(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    repository = Mcd64Repository(
        database
    )

    first_run = (
        database.start_import(
            "burned_pixels_tif",
            "burn_raster_A.tif",
        )
    )

    second_run = (
        database.start_import(
            "burned_pixels_tif",
            "burn_raster_B.tif",
        )
    )

    first_row = _base_row(
        dedupe_key="source-A"
    )

    second_row = _base_row(
        dedupe_key="source-B"
    )

    first = repository.store_rows(
        [first_row],
        import_run_id=first_run,
    )

    second = repository.store_rows(
        [second_row],
        import_run_id=second_run,
    )

    assert (
        first.inserted_pixels
        == 1
    )

    assert (
        second.inserted_pixels
        == 0
    )

    assert (
        second.existing_pixels
        == 1
    )

    with database.connect() as conn:
        pixel_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM burned_pixels
            """
        ).fetchone()[0]

        membership_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM burned_pixel_run_membership
                """
            ).fetchone()[0]
        )

    assert pixel_count == 1
    assert membership_count == 2


def test_same_run_membership_is_not_duplicated(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    repository = Mcd64Repository(
        database
    )

    run_id = database.start_import(
        "burned_pixels_tif",
        "burn.tif",
    )

    row = _base_row(
        dedupe_key="source-A"
    )

    repository.store_rows(
        [row],
        import_run_id=run_id,
    )

    second = repository.store_rows(
        [row],
        import_run_id=run_id,
    )

    assert (
        second.existing_pixels
        == 1
    )

    assert (
        second.run_memberships_added
        == 0
    )

    assert (
        second.run_memberships_existing
        == 1
    )

    assert len(
        repository.list_run_pixels(
            run_id
        )
    ) == 1


def test_migration_3_merges_legacy_duplicate_pixels(
    tmp_path,
):
    db_path = (
        tmp_path / "legacy.sqlite"
    )

    with sqlite3.connect(
        db_path
    ) as conn:
        conn.execute(
            """
            CREATE TABLE burned_pixels (
                id INTEGER PRIMARY KEY,
                dedupe_key TEXT NOT NULL UNIQUE,
                burned_date TEXT NOT NULL,
                doy INTEGER,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                region_name TEXT,
                cell_area_km2 REAL NOT NULL,
                source_product TEXT NOT NULL,
                raster_name TEXT,
                qa_value INTEGER,
                import_run_id INTEGER
            )
            """
        )

        conn.execute(
            """
            INSERT INTO burned_pixels(
                dedupe_key,
                burned_date,
                doy,
                latitude,
                longitude,
                region_name,
                cell_area_km2,
                source_product,
                raster_name,
                qa_value,
                import_run_id
            )
            VALUES (
                'legacy-A',
                '2026-03-15',
                74,
                45.75,
                126.65,
                '测试区域',
                0.247,
                'MCD64A1',
                'A.tif',
                3,
                NULL
            )
            """
        )

        conn.execute(
            """
            INSERT INTO burned_pixels(
                dedupe_key,
                burned_date,
                doy,
                latitude,
                longitude,
                region_name,
                cell_area_km2,
                source_product,
                raster_name,
                qa_value,
                import_run_id
            )
            VALUES (
                'legacy-B',
                '2026-03-15',
                74,
                45.75,
                126.65,
                '测试区域',
                0.247,
                'MCD64A1',
                'B.tif',
                3,
                NULL
            )
            """
        )

        conn.execute(
            "PRAGMA user_version = 2"
        )

    database = Database(
        db_path
    )

    database.initialize()

    with database.connect() as conn:
        version = conn.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT
                canonical_key
            FROM burned_pixels
            """
        ).fetchall()

    assert version == 3

    # 同一规范烧毁像元只保留一次。
    assert len(rows) == 1

    assert (
        rows[0][
            "canonical_key"
        ]
        is not None
    )