# Day4：FIRMS处理的网页重复执行及无行政边界阻断测试

from io import BytesIO

from fire_monitor.app import (
    create_app,
)


def _create_app(
    tmp_path,
):
    return create_app(
        database_path=(
            tmp_path / "test.sqlite"
        ),
        uploads_root=(
            tmp_path / "uploads"
        ),
        testing=True,
    )


def _add_region(
    app,
):
    database = app.extensions[
        "fire_database"
    ]

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


def _create_task(
    client,
):
    response = client.post(
        "/tasks",
        data={
            "name": (
                "FIRMS 网页正式处理"
            ),
            "analysis_scope": (
                "firms_only"
            ),
            "analysis_start": (
                "2026-03-01"
            ),
            "analysis_end": (
                "2026-03-31"
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    return (
        response.headers["Location"]
        .rstrip("/")
        .split("/")[-1]
    )


def _upload_firms(
    client,
    task_id: str,
):
    content = (
        "latitude,longitude,acq_date,"
        "acq_time,instrument,satellite,"
        "confidence,version,frp\n"

        "45.75,126.65,2026-03-15,"
        "325,VIIRS,N,n,2.0NRT,8.5\n"

        "45.75,126.65,2026-03-15,"
        "325,VIIRS,N,n,2.0NRT,8.5\n"

        "45.80,126.70,2026-03-15,"
        "330,VIIRS,N,l,2.0NRT,7.0\n"
    ).encode(
        "utf-8"
    )

    response = client.post(
        f"/tasks/{task_id}/files",
        data={
            "file_role": "firms_csv",
            "file": (
                BytesIO(content),
                "firms_full.csv",
            ),
        },
        content_type=(
            "multipart/form-data"
        ),
        follow_redirects=False,
    )

    assert response.status_code == 302


def test_web_can_execute_firms_processing(
    tmp_path,
):
    app = _create_app(
        tmp_path
    )

    _add_region(app)

    client = app.test_client()

    task_id = _create_task(
        client
    )

    _upload_firms(
        client,
        task_id,
    )

    response = client.post(
        f"/tasks/{task_id}/process/firms",
        follow_redirects=True,
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "FIRMS 处理记录" in page

    database = app.extensions[
        "fire_database"
    ]

    with database.connect() as conn:
        observation_count = (
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

    # 两条相同 nominal 记录只算一个观测；
    # low confidence 被质量筛除。
    assert observation_count == 1
    assert source_count == 1

    runs = database.list_import_runs(
        task_id=task_id,
        data_kind=(
            "active_fire_observations"
        ),
    )

    assert len(runs) == 1

    report = runs[0]["metadata"]

    assert (
        report["input_rows"]
        == 3
    )

    assert (
        report[
            "normalization_rejected"
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
            "new_observations"
        ]
        == 1
    )


def test_repeated_web_processing_does_not_duplicate_observation(
    tmp_path,
):
    app = _create_app(
        tmp_path
    )

    _add_region(app)

    client = app.test_client()

    task_id = _create_task(
        client
    )

    _upload_firms(
        client,
        task_id,
    )

    first = client.post(
        f"/tasks/{task_id}/process/firms"
    )

    second = client.post(
        f"/tasks/{task_id}/process/firms"
    )

    assert first.status_code == 302
    assert second.status_code == 302

    database = app.extensions[
        "fire_database"
    ]

    with database.connect() as conn:
        observation_count = (
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

    assert observation_count == 1
    assert source_count == 1

    runs = database.list_import_runs(
        task_id=task_id,
        data_kind=(
            "active_fire_observations"
        ),
    )

    assert len(runs) == 2

    latest = runs[0]["metadata"]

    assert (
        latest["new_observations"]
        == 0
    )

    assert (
        latest[
            "existing_observations"
        ]
        == 1
    )

    assert (
        latest[
            "source_records_existing"
        ]
        == 1
    )


def test_web_does_not_process_firms_without_regions(
    tmp_path,
):
    app = _create_app(
        tmp_path
    )

    client = app.test_client()

    task_id = _create_task(
        client
    )

    _upload_firms(
        client,
        task_id,
    )

    response = client.post(
        f"/tasks/{task_id}/process/firms",
        follow_redirects=False,
    )

    assert response.status_code == 400

    page = response.get_data(
        as_text=True
    )

    assert "尚未导入行政区边界" in page

    database = app.extensions[
        "fire_database"
    ]

    with database.connect() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM active_fire_observations
            """
        ).fetchone()[0]

    assert count == 0