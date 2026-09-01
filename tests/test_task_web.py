from io import BytesIO
from pathlib import Path

from fire_monitor.app import create_app


def _create_test_app(
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


def _create_firms_task(
    client,
) -> str:
    response = client.post(
        "/tasks",
        data={
            "name": "网页 FIRMS 测试",
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

    location = response.headers[
        "Location"
    ]

    assert "/tasks/TASK-" in location

    return location.rstrip(
        "/"
    ).split("/")[-1]


def test_tasks_page_loads(
    tmp_path,
):
    app = _create_test_app(
        tmp_path
    )

    client = app.test_client()

    response = client.get(
        "/tasks"
    )

    assert response.status_code == 200
    assert "创建分析任务" in (
        response.get_data(
            as_text=True
        )
    )


def test_web_can_create_task(
    tmp_path,
):
    app = _create_test_app(
        tmp_path
    )

    client = app.test_client()

    task_id = _create_firms_task(
        client
    )

    database = app.extensions[
        "fire_database"
    ]

    task = (
        database
        .get_analysis_task(task_id)
    )

    assert task is not None

    assert task["name"] == (
        "网页 FIRMS 测试"
    )

    assert (
        task["parameters"][
            "analysis_scope"
        ]
        == "firms_only"
    )


def test_web_uploads_real_firms_file_and_becomes_ready(
    tmp_path,
):
    app = _create_test_app(
        tmp_path
    )

    client = app.test_client()

    task_id = _create_firms_task(
        client
    )

    firms_content = (
        "latitude,longitude,acq_date,"
        "instrument,confidence\n"
        "45.75,126.65,2026-03-15,"
        "VIIRS,n\n"
    ).encode("utf-8")

    response = client.post(
        f"/tasks/{task_id}/files",
        data={
            "file_role": "firms_csv",
            "file": (
                BytesIO(
                    firms_content
                ),
                "firms.csv",
            ),
        },
        content_type=(
            "multipart/form-data"
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "READY" in page
    assert "firms.csv" in page
    assert "valid" in page

    database = app.extensions[
        "fire_database"
    ]

    task = (
        database
        .get_analysis_task(task_id)
    )

    assert task is not None
    assert task["status"] == "ready"

    files = (
        database
        .list_input_files(task_id)
    )

    assert len(files) == 1

    record = files[0]

    assert (
        record[
            "validation_status"
        ]
        == "valid"
    )

    stored_path = Path(
        record["stored_path"]
    )

    assert stored_path.is_file()

    assert (
        stored_path.read_bytes()
        == firms_content
    )


def test_invalid_web_upload_is_recorded_but_not_ready(
    tmp_path,
):
    app = _create_test_app(
        tmp_path
    )

    client = app.test_client()

    task_id = _create_firms_task(
        client
    )

    bad_content = (
        "latitude,acq_date\n"
        "45.75,2026-03-15\n"
    ).encode("utf-8")

    response = client.post(
        f"/tasks/{task_id}/files",
        data={
            "file_role": "firms_csv",
            "file": (
                BytesIO(
                    bad_content
                ),
                "bad.csv",
            ),
        },
        content_type=(
            "multipart/form-data"
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert "NOT READY" in page
    assert "invalid" in page

    database = app.extensions[
        "fire_database"
    ]

    files = (
        database
        .list_input_files(task_id)
    )

    assert len(files) == 1

    assert (
        files[0][
            "validation_status"
        ]
        == "invalid"
    )


def test_task_rejects_missing_upload(
    tmp_path,
):
    app = _create_test_app(
        tmp_path
    )

    client = app.test_client()

    task_id = _create_firms_task(
        client
    )

    response = client.post(
        f"/tasks/{task_id}/files",
        data={
            "file_role": "firms_csv",
        },
        content_type=(
            "multipart/form-data"
        ),
    )

    assert response.status_code == 400

    assert "请选择需要上传的文件" in (
        response.get_data(
            as_text=True
        )
    )

def test_unknown_page_returns_404(
    tmp_path,
):
    app = _create_test_app(
        tmp_path
    )

    client = app.test_client()

    response = client.get(
        "/this-page-does-not-exist"
    )

    assert response.status_code == 404