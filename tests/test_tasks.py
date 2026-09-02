# Day2：分析任务、输入文件登记、数据库迁移及任务状态生命周期测试

import sqlite3

import pytest

from fire_monitor.services.task_service import TaskService
from fire_monitor.storage.database import Database


def test_database_migration_creates_task_tables(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"

    database = Database(db_path)
    database.initialize()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        version = conn.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

    assert "analysis_tasks" in tables
    assert "input_files" in tables
    assert "boundary_sets" in tables
    assert version == 2


def test_existing_tables_are_preserved(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"

    database = Database(db_path)
    database.initialize()

    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO import_runs(
                data_kind,
                source_ref,
                started_at,
                status
            )
            VALUES (
                'firms',
                'legacy-fixture',
                '2026-01-01T00:00:00+00:00',
                'completed'
            )
            """
        )

    database.initialize()

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT source_ref
            FROM import_runs
            WHERE source_ref = 'legacy-fixture'
            """
        ).fetchone()

    assert row is not None
    assert row["source_ref"] == "legacy-fixture"


def test_create_and_read_analysis_task(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    service = TaskService(database)

    task = service.create_task(
        "2026年春季火情分析",
        analysis_start="2026-03-01",
        analysis_end="2026-03-31",
        assessment_mode="relative_attention",
        parameters={
            "quality_only": True,
        },
    )

    assert task["task_id"].startswith(
        "TASK-"
    )
    assert task["name"] == (
        "2026年春季火情分析"
    )
    assert task["status"] == "created"
    assert task["analysis_start"] == (
        "2026-03-01"
    )
    assert task["analysis_end"] == (
        "2026-03-31"
    )
    assert task["software_version"] == (
        "0.1.1"
    )
    assert task["parameters"] == {
        "quality_only": True
    }

    loaded = service.get_task(
        task["task_id"]
    )

    assert loaded is not None
    assert loaded["task_id"] == (
        task["task_id"]
    )


def test_task_rejects_invalid_date_range(
    tmp_path,
):
    service = TaskService(
        Database(
            tmp_path / "test.sqlite"
        )
    )

    with pytest.raises(ValueError):
        service.create_task(
            "错误日期任务",
            analysis_start="2026-04-01",
            analysis_end="2026-03-01",
        )


def test_register_input_file(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )
    service = TaskService(database)

    task = service.create_task(
        "输入文件登记测试"
    )

    file_id = database.register_input_file(
        task_id=task["task_id"],
        file_role="firms_csv",
        original_filename="firms.csv",
        sha256="a" * 64,
        size_bytes=1024,
        source_agency="NASA FIRMS",
        product_name="VIIRS",
        processing_class="SP",
    )

    assert file_id > 0

    files = database.list_input_files(
        task["task_id"]
    )

    assert len(files) == 1
    assert files[0]["original_filename"] == (
        "firms.csv"
    )
    assert files[0]["file_role"] == (
        "firms_csv"
    )
    assert files[0]["validation_status"] == (
        "pending"
    )


def test_task_status_lifecycle(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )
    service = TaskService(database)

    task = service.create_task(
        "状态测试"
    )

    service.mark_running(
        task["task_id"]
    )

    running = service.get_task(
        task["task_id"]
    )

    assert running["status"] == "running"
    assert running["started_at"] is not None

    service.mark_completed(
        task["task_id"]
    )

    completed = service.get_task(
        task["task_id"]
    )

    assert completed["status"] == (
        "completed"
    )
    assert completed["completed_at"] is not None