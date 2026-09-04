# Day5C-2：任务级MCD64A1正式处理、QA筛选、面积统计及运行追溯测试

from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from fire_monitor.services.mcd64_processing_service import (
    Mcd64ProcessingService,
)
from fire_monitor.services.task_service import (
    TaskService,
)
from fire_monitor.services.validation_service import (
    ValidationService,
)
from fire_monitor.storage.database import (
    Database,
)


gdal.UseExceptions()


def _create_geotiff(
    path: Path,
    values: np.ndarray,
    *,
    data_type: int,
) -> None:
    height, width = values.shape

    driver = gdal.GetDriverByName(
        "GTiff"
    )

    dataset = driver.Create(
        str(path),
        width,
        height,
        1,
        data_type,
    )

    assert dataset is not None

    dataset.SetGeoTransform(
        (
            125.0,
            0.01,
            0.0,
            48.0,
            0.0,
            -0.01,
        )
    )

    srs = osr.SpatialReference()

    assert (
        srs.ImportFromEPSG(4326)
        == 0
    )

    dataset.SetProjection(
        srs.ExportToWkt()
    )

    band = dataset.GetRasterBand(1)

    band.WriteArray(values)
    band.FlushCache()

    dataset.FlushCache()
    dataset = None


def _add_region(
    database: Database,
) -> None:
    database.upsert_regions(
        [
            {
                "name": "测试区域",
                "level": "city",
                "source": "test",
                "version": "1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [125.0, 47.97],
                            [125.03, 47.97],
                            [125.03, 48.0],
                            [125.0, 48.0],
                            [125.0, 47.97],
                        ]
                    ],
                },
            }
        ]
    )


def _services(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    database.initialize()

    _add_region(database)

    task_service = TaskService(
        database
    )

    validation_service = (
        ValidationService(
            database,
            uploads_root=(
                tmp_path / "uploads"
            ),
        )
    )

    processing_service = (
        Mcd64ProcessingService(
            database
        )
    )

    return (
        database,
        task_service,
        validation_service,
        processing_service,
    )


def _create_pair(
    tmp_path,
) -> tuple[
    Path,
    Path,
]:
    burn_path = (
        tmp_path
        / "MCD64A1.A2026060.burndate.tif"
    )

    qa_path = (
        tmp_path
        / "MCD64A1.A2026060.qa.tif"
    )

    burn_values = np.array(
        [
            [60, 61, 62, 0],
            [63, 91, 64, 65],
        ],
        dtype=np.int16,
    )

    qa_values = np.array(
        [
            [3, 7, 0, 3],
            [35, 3, 11, 3],
        ],
        dtype=np.uint8,
    )

    _create_geotiff(
        burn_path,
        burn_values,
        data_type=(
            gdal.GDT_Int16
        ),
    )

    _create_geotiff(
        qa_path,
        qa_values,
        data_type=(
            gdal.GDT_Byte
        ),
    )

    return (
        burn_path,
        qa_path,
    )


def _create_task_and_upload_pair(
    tmp_path,
    task_service,
    validation,
):
    task = task_service.create_task(
        "MCD64A1 正式处理",
        parameters={
            "analysis_scope": (
                "mcd64_only"
            ),
        },
    )

    (
        burn_path,
        qa_path,
    ) = _create_pair(
        tmp_path
    )

    burn_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=burn_path,
            file_role=(
                "mcd64_burn_date"
            ),
        )
    )

    qa_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=qa_path,
            file_role=(
                "mcd64_qa"
            ),
        )
    )

    return (
        task,
        burn_record,
        qa_record,
    )


def test_task_mcd64_standard_processing(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    (
        task,
        burn_record,
        qa_record,
    ) = _create_task_and_upload_pair(
        tmp_path,
        task_service,
        validation,
    )

    report = (
        processing.process_pair(
            task_id=(
                task["task_id"]
            ),
            burn_file_id=(
                burn_record["id"]
            ),
            qa_file_id=(
                qa_record["id"]
            ),
            qa_policy="standard",
        )
    )

    assert (
        report[
            "positive_burn_date_pixels"
        ]
        == 7
    )

    assert (
        report[
            "qa_rejected_pixels"
        ]
        == 2
    )

    assert (
        report[
            "outside_configured_regions"
        ]
        == 1
    )

    assert (
        report[
            "run_burned_pixel_count"
        ]
        == 3
    )

    assert (
        report[
            "run_burned_area_km2"
        ]
        > 0
    )

    assert (
        report[
            "new_burned_pixels"
        ]
        == 3
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

    assert pixel_count == 3
    assert membership_count == 3

    with database.connect() as conn:
        rows = conn.execute(
            """
            SELECT region_name
            FROM burned_pixels
            """
        ).fetchall()

    assert rows
    assert rows[0]["region_name"] == "测试区域"

def test_repeated_processing_does_not_duplicate_pixels(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    (
        task,
        burn_record,
        qa_record,
    ) = _create_task_and_upload_pair(
        tmp_path,
        task_service,
        validation,
    )

    first = processing.process_pair(
        task_id=(
            task["task_id"]
        ),
        burn_file_id=(
            burn_record["id"]
        ),
        qa_file_id=(
            qa_record["id"]
        ),
    )

    second = processing.process_pair(
        task_id=(
            task["task_id"]
        ),
        burn_file_id=(
            burn_record["id"]
        ),
        qa_file_id=(
            qa_record["id"]
        ),
    )

    assert (
        first[
            "new_burned_pixels"
        ]
        == 3
    )

    assert (
        second[
            "new_burned_pixels"
        ]
        == 0
    )

    assert (
        second[
            "existing_burned_pixels"
        ]
        == 3
    )

    # 第二次运行仍然拥有自己的
    # 3 个 membership。
    assert (
        second[
            "run_burned_pixel_count"
        ]
        == 3
    )

    with database.connect() as conn:
        pixel_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM burned_pixels
            """
        ).fetchone()[0]

        run_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM import_runs
            WHERE data_kind =
                'burned_pixels_tif'
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

    assert pixel_count == 3
    assert run_count == 2

    # 两次运行，每次接受三个像元。
    assert membership_count == 6


def test_strict_processing_has_smaller_result(
    tmp_path,
):
    (
        _database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    (
        task,
        burn_record,
        qa_record,
    ) = _create_task_and_upload_pair(
        tmp_path,
        task_service,
        validation,
    )

    standard = (
        processing.process_pair(
            task_id=(
                task["task_id"]
            ),
            burn_file_id=(
                burn_record["id"]
            ),
            qa_file_id=(
                qa_record["id"]
            ),
            qa_policy="standard",
        )
    )

    strict = (
        processing.process_pair(
            task_id=(
                task["task_id"]
            ),
            burn_file_id=(
                burn_record["id"]
            ),
            qa_file_id=(
                qa_record["id"]
            ),
            qa_policy="strict",
        )
    )

    assert (
        standard[
            "run_burned_pixel_count"
        ]
        == 3
    )

    assert (
        strict[
            "run_burned_pixel_count"
        ]
        == 2
    )

    assert (
        strict[
            "run_burned_area_km2"
        ]
        <
        standard[
            "run_burned_area_km2"
        ]
    )


def test_import_run_traces_burn_and_qa_files(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    (
        task,
        burn_record,
        qa_record,
    ) = _create_task_and_upload_pair(
        tmp_path,
        task_service,
        validation,
    )

    report = (
        processing.process_pair(
            task_id=(
                task["task_id"]
            ),
            burn_file_id=(
                burn_record["id"]
            ),
            qa_file_id=(
                qa_record["id"]
            ),
        )
    )

    runs = database.list_import_runs(
        task_id=(
            task["task_id"]
        ),
        data_kind=(
            "burned_pixels_tif"
        ),
    )

    assert len(runs) == 1

    run = runs[0]

    assert run["status"] == "completed"

    assert (
        run["input_file_id"]
        == burn_record["id"]
    )

    metadata = run["metadata"]

    assert (
        metadata["burn_file_id"]
        == burn_record["id"]
    )

    assert (
        metadata["qa_file_id"]
        == qa_record["id"]
    )

    assert (
        metadata["run_id"]
        == report["run_id"]
    )


def test_firms_only_task_cannot_process_mcd64(
    tmp_path,
):
    (
        _database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "错误分析范围",
        parameters={
            "analysis_scope": (
                "firms_only"
            ),
        },
    )

    (
        burn_path,
        qa_path,
    ) = _create_pair(
        tmp_path
    )

    burn_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=burn_path,
            file_role=(
                "mcd64_burn_date"
            ),
        )
    )

    qa_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=qa_path,
            file_role=(
                "mcd64_qa"
            ),
        )
    )

    try:
        processing.process_pair(
            task_id=(
                task["task_id"]
            ),
            burn_file_id=(
                burn_record["id"]
            ),
            qa_file_id=(
                qa_record["id"]
            ),
        )

    except ValueError as exc:
        assert (
            "不包含 MCD64A1"
            in str(exc)
        )

    else:
        raise AssertionError(
            "firms_only 任务不应允许"
            "执行 MCD64A1 正式处理。"
        )