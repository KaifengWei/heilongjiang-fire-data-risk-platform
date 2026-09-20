from __future__ import annotations

from fire_monitor.app import create_app
from fire_monitor.services.task_service import TaskService
from fire_monitor.storage.database import Database


def test_task_record_can_be_renamed_and_hidden_without_deleting_underlying_data(tmp_path):
    database = Database(tmp_path / "record_management.sqlite")
    service = TaskService(database)

    task = service.create_task(
        "原始名称",
        analysis_start="2026-08-01",
        analysis_end="2026-08-31",
        assessment_mode="relative_attention",
        parameters={"analysis_scope": "firms_only"},
    )

    database.register_input_file(
        task_id=task["task_id"],
        file_role="firms_csv",
        original_filename="firms.csv",
        sha256="abc123",
        size_bytes=123,
        validation_status="valid",
    )

    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO active_fire_observations(
                dedupe_key,
                acquired_date,
                acquired_time,
                latitude,
                longitude,
                region_name,
                firms_source,
                confidence,
                frp,
                quality_rule
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "keep-me",
                "2026-08-01",
                "0300",
                45.0,
                126.0,
                "哈尔滨市",
                "TEST",
                "n",
                10.0,
                "test",
            ),
        )

    service.rename_task(task["task_id"], "用户自定义名称")
    renamed = service.get_task(task["task_id"])

    assert renamed is not None
    assert renamed["name"] == "用户自定义名称"

    service.hide_task(task["task_id"])

    assert service.get_task(task["task_id"]) is None
    assert all(
        row["task_id"] != task["task_id"]
        for row in service.list_tasks()
    )

    raw_task = database.get_analysis_task(task["task_id"])
    assert raw_task is not None
    assert raw_task["parameters"]["record_hidden"] is True
    assert len(database.list_input_files(task["task_id"])) == 1

    with database.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM active_fire_observations WHERE dedupe_key = ?",
            ("keep-me",),
        ).fetchone()[0]

    assert count == 1


def test_record_management_web_routes(tmp_path):
    app = create_app(
        database_path=tmp_path / "web.sqlite",
        testing=True,
        uploads_root=tmp_path / "uploads",
    )

    service = app.extensions["task_service"]
    task = service.create_task(
        "待修改名称",
        assessment_mode="relative_attention",
        parameters={"analysis_scope": "firms_only"},
    )

    client = app.test_client()

    response = client.post(
        f"/tasks/{task['task_id']}/rename",
        data={"name": "新的记录名称", "return_to": "tasks"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert service.get_task(task["task_id"])["name"] == "新的记录名称"

    response = client.post(
        f"/tasks/{task['task_id']}/delete",
        data={"return_to": "tasks"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert service.get_task(task["task_id"]) is None
