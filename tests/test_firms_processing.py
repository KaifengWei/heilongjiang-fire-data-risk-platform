# Day4C：任务级FIRMS正式处理、日期约束、行政区落区及处理追溯测试

from pathlib import Path

from fire_monitor.services.firms_processing_service import (
    FirmsProcessingService,
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


def _add_test_region(
    database: Database,
) -> None:
    """增加一个简单矩形测试区域。"""

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
                            [125.0, 45.0],
                            [128.0, 45.0],
                            [128.0, 48.0],
                            [125.0, 48.0],
                            [125.0, 45.0],
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

    _add_test_region(
        database
    )

    task_service = (
        TaskService(database)
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
        FirmsProcessingService(
            database
        )
    )

    return (
        database,
        task_service,
        validation_service,
        processing_service,
    )


def test_task_firms_processing_report(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "FIRMS 正式处理测试",
        analysis_start=(
            "2026-03-01"
        ),
        analysis_end=(
            "2026-03-31"
        ),
        parameters={
            "analysis_scope": (
                "firms_only"
            ),
        },
    )

    source = (
        tmp_path / "firms.csv"
    )

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "acq_time,instrument,satellite,"
            "confidence,version,frp\n"

            # 正常记录
            "45.75,126.65,2026-03-15,"
            "325,VIIRS,N,n,2.0NRT,8.5\n"

            # 同文件完全重复
            "45.75,126.65,2026-03-15,"
            "325,VIIRS,N,n,2.0NRT,8.5\n"

            # VIIRS low：质量筛除
            "45.80,126.70,2026-03-15,"
            "330,VIIRS,N,l,2.0NRT,7.0\n"

            # 纬度非法
            "999,126.65,2026-03-15,"
            "335,VIIRS,N,n,2.0NRT,7.0\n"

            # 超出行政区
            "50.00,130.00,2026-03-15,"
            "340,VIIRS,N,n,2.0NRT,6.0\n"

            # 超出任务日期
            "45.90,126.80,2026-04-05,"
            "345,VIIRS,N,n,2.0NRT,6.0\n"
        ),
        encoding="utf-8",
    )

    file_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=source,
            file_role="firms_csv",
        )
    )

    report = (
        processing
        .process_input_file(
            task_id=(
                task["task_id"]
            ),
            input_file_id=(
                file_record["id"]
            ),
        )
    )

    assert (
        report["input_rows"]
        == 6
    )

    assert (
        report[
            "normalization_accepted"
        ]
        == 4
    )

    assert (
        report[
            "normalization_rejected"
        ]
        == 2
    )

    assert (
        report[
            "rejection_counts"
        ][
            "invalid_latitude"
        ]
        == 1
    )

    assert (
        report[
            "rejection_counts"
        ][
            "quality_rejected"
        ]
        == 1
    )

    assert (
        report[
            "outside_task_date_range"
        ]
        == 1
    )

    assert (
        report[
            "outside_configured_regions"
        ]
        == 1
    )

    assert (
        report[
            "duplicate_source_records_in_file"
        ]
        == 1
    )

    assert (
        report[
            "rows_ready_for_storage"
        ]
        == 1
    )

    assert (
        report[
            "new_observations"
        ]
        == 1
    )

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT
                region_name,
                acquired_date,
                acquired_time,
                processing_class
            FROM active_fire_observations
            """
        ).fetchone()

    assert row is not None
    assert (
        row["region_name"]
        == "测试区域"
    )

    assert (
        row["acquired_date"]
        == "2026-03-15"
    )

    assert (
        row["acquired_time"]
        == "0325"
    )

    assert (
        row["processing_class"]
        == "NRT"
    )


def test_import_run_links_task_and_input_file(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "追溯测试",
        parameters={
            "analysis_scope": (
                "firms_only"
            ),
        },
    )

    source = (
        tmp_path / "firms.csv"
    )

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "acq_time,instrument,satellite,"
            "confidence,version\n"
            "45.75,126.65,2026-03-15,"
            "325,VIIRS,N,n,2.0NRT\n"
        ),
        encoding="utf-8",
    )

    file_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=source,
            file_role="firms_csv",
        )
    )

    report = (
        processing
        .process_input_file(
            task_id=(
                task["task_id"]
            ),
            input_file_id=(
                file_record["id"]
            ),
        )
    )

    with database.connect() as conn:
        run = conn.execute(
            """
            SELECT
                task_id,
                input_file_id,
                status,
                input_count,
                stored_count
            FROM import_runs
            WHERE id = ?
            """,
            (
                report["run_id"],
            ),
        ).fetchone()

    assert run is not None

    assert (
        run["task_id"]
        == task["task_id"]
    )

    assert (
        run["input_file_id"]
        == file_record["id"]
    )

    assert (
        run["status"]
        == "completed"
    )

    assert run["input_count"] == 1
    assert run["stored_count"] == 1


def test_task_processing_replaces_nrt_with_sp(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        processing,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "NRT SP 任务测试",
        parameters={
            "analysis_scope": (
                "firms_only"
            ),
        },
    )

    nrt_path = (
        tmp_path / "nrt.csv"
    )

    sp_path = (
        tmp_path / "sp.csv"
    )

    common_prefix = (
        "latitude,longitude,acq_date,"
        "acq_time,instrument,satellite,"
        "confidence,version\n"
    )

    nrt_path.write_text(
        common_prefix
        + (
            "45.75,126.65,2026-03-15,"
            "325,VIIRS,N,n,2.0NRT\n"
        ),
        encoding="utf-8",
    )

    sp_path.write_text(
        common_prefix
        + (
            "45.75,126.65,2026-03-15,"
            "325,VIIRS,N,n,2.0\n"
        ),
        encoding="utf-8",
    )

    nrt_file = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=nrt_path,
            file_role="firms_csv",
        )
    )

    sp_file = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=sp_path,
            file_role="firms_csv",
        )
    )

    first = (
        processing
        .process_input_file(
            task_id=(
                task["task_id"]
            ),
            input_file_id=(
                nrt_file["id"]
            ),
        )
    )

    second = (
        processing
        .process_input_file(
            task_id=(
                task["task_id"]
            ),
            input_file_id=(
                sp_file["id"]
            ),
        )
    )

    assert (
        first[
            "new_observations"
        ]
        == 1
    )

    assert (
        second[
            "new_observations"
        ]
        == 0
    )

    assert (
        second[
            "existing_observations"
        ]
        == 1
    )

    assert (
        second[
            "preferred_source_updates"
        ]
        == 1
    )

    with database.connect() as conn:
        observations = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM active_fire_observations
                """
            ).fetchone()[0]
        )

        source_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM active_fire_observation_sources
                """
            ).fetchone()[0]
        )

        observation = (
            conn.execute(
                """
                SELECT processing_class
                FROM active_fire_observations
                """
            ).fetchone()
        )

    assert observations == 1
    assert source_count == 2

    assert (
        observation[
            "processing_class"
        ]
        == "SP"
    )


def test_mcd64_only_task_cannot_process_firms(
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
                "mcd64_only"
            ),
        },
    )

    source = (
        tmp_path / "firms.csv"
    )

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "acq_time,instrument,satellite,"
            "confidence,version\n"
            "45.75,126.65,2026-03-15,"
            "325,VIIRS,N,n,2.0NRT\n"
        ),
        encoding="utf-8",
    )

    file_record = (
        validation
        .receive_local_file(
            task_id=(
                task["task_id"]
            ),
            source_path=source,
            file_role="firms_csv",
        )
    )

    try:
        processing.process_input_file(
            task_id=(
                task["task_id"]
            ),
            input_file_id=(
                file_record["id"]
            ),
        )

    except ValueError as exc:
        assert (
            "不包含 FIRMS"
            in str(exc)
        )

    else:
        raise AssertionError(
            "mcd64_only 任务不应允许"
            "执行 FIRMS 正式处理"
        )