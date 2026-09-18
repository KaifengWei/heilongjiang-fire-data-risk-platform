from io import BytesIO

from fire_monitor.app import create_app


def _app_with_region(tmp_path):
    app = create_app(
        database_path=tmp_path / "test.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    database = app.extensions["fire_database"]
    database.upsert_regions(
        [
            {
                "name": "哈尔滨市",
                "level": "city",
                "source": "test",
                "version": "1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [125.0, 45.0],
                        [128.0, 45.0],
                        [128.0, 47.0],
                        [125.0, 47.0],
                        [125.0, 45.0],
                    ]],
                },
            }
        ]
    )
    return app


def _firms_bytes():
    return (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "45.75,126.65,2026-03-15,0320,N,VIIRS,n,2.0NRT,8.5\n"
    ).encode("utf-8")


def test_home_is_upload_first_and_does_not_require_manual_dates(tmp_path):
    app = _app_with_region(tmp_path)
    response = app.test_client().get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "上传遥感数据并开始分析" in page
    assert "开始日期" not in page
    assert "地图点位" not in page
    assert "分析记录" in page


def test_auto_firms_upload_detects_period_processes_and_creates_record(tmp_path):
    app = _app_with_region(tmp_path)
    client = app.test_client()

    response = client.post(
        "/analyze",
        data={
            "files": (
                BytesIO(_firms_bytes()),
                "firms.csv",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "2026-03-15" in page
    assert "FIRMS" in page
    assert "哈尔滨市" in page
    assert "1" in page

    database = app.extensions["fire_database"]
    tasks = database.list_analysis_tasks()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["analysis_start"] == "2026-03-15"
    assert task["analysis_end"] == "2026-03-15"
    assert task["parameters"]["analysis_scope"] == "firms_only"
    assert task["parameters"]["auto_analysis"] is True
    assert task["status"] == "completed"

    rows = app.extensions["statistics_service"].task_region_statistics(task["task_id"])
    assert rows[0]["region_name"] == "哈尔滨市"
    assert rows[0]["active_fire_count"] == 1


def test_second_analysis_reuses_existing_observation_but_keeps_task_result(tmp_path):
    app = _app_with_region(tmp_path)
    client = app.test_client()

    task_ids = []

    for _ in range(2):
        response = client.post(
            "/analyze",
            data={
                "files": (
                    BytesIO(_firms_bytes()),
                    "firms.csv",
                )
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 302

        task_id = (
            response.headers["Location"]
            .rstrip("/")
            .split("/")[-1]
        )

        task_ids.append(task_id)

    database = app.extensions["fire_database"]
    tasks = database.list_analysis_tasks()
    assert len(tasks) == 2

    with database.connect() as conn:
        global_count = conn.execute(
            "SELECT COUNT(*) FROM active_fire_observations"
        ).fetchone()[0]

    assert global_count == 1

    second_task_id = task_ids[1]

    rows = app.extensions["statistics_service"].task_region_statistics(
        second_task_id
    )
    assert rows[0]["active_fire_count"] == 1

    runs = database.list_import_runs(
        task_id=second_task_id,
        data_kind="active_fire_observations",
    )
    assert runs[0]["metadata"]["new_observations"] == 0
    assert runs[0]["metadata"]["existing_observations"] == 1
