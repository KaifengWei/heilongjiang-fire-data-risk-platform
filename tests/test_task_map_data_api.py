from __future__ import annotations

from fire_monitor.app import create_app
from fire_monitor.services.task_service import TaskService
from fire_monitor.storage.database import Database


def test_task_map_data_api_returns_compact_points(tmp_path):
    app = create_app(
        database_path=tmp_path / "map.sqlite",
        testing=True,
        uploads_root=tmp_path / "uploads",
    )

    database = app.extensions["fire_database"]
    task_service = app.extensions["task_service"]

    task = task_service.create_task(
        "地图接口测试",
        analysis_start="2026-08-01",
        analysis_end="2026-08-02",
        assessment_mode="relative_attention",
        parameters={"analysis_scope": "firms_only"},
    )

    run_id = database.start_import(
        "active_fire_observations",
        "map-test",
        task_id=task["task_id"],
    )

    with database.connect() as conn:
        cursor = conn.execute(
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
                quality_rule,
                import_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "map-point-1",
                "2026-08-01",
                "0300",
                45.0,
                126.0,
                "哈尔滨市",
                "TEST",
                "n",
                12.5,
                "test",
                run_id,
            ),
        )
        observation_id = int(cursor.lastrowid)

        conn.execute(
            """
            INSERT INTO active_fire_run_membership(
                run_id,
                observation_id,
                created_at
            )
            VALUES (?, ?, datetime('now'))
            """,
            (
                run_id,
                observation_id,
            ),
        )

    database.finish_import(
        run_id,
        input_count=1,
        stored_count=1,
        status="completed",
    )

    client = app.test_client()

    response = client.get(
        f"/api/tasks/{task['task_id']}/map-data"
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["dates"] == ["2026-08-01"]
    assert payload["regions"] == ["哈尔滨市"]
    assert payload["point_count"] == 1
    assert payload["points"][0][:4] == [
        126.0,
        45.0,
        0,
        0,
    ]
    assert payload["points"][0][4] == 12.5
