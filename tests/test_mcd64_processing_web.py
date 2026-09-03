# Day5D：MCD64A1正式处理的网页调用、QA策略传递及无行政边界阻断测试

from io import BytesIO
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from fire_monitor.app import (
    create_app,
)


gdal.UseExceptions()


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


def _create_geotiff(
    path: Path,
    values: np.ndarray,
    *,
    data_type: int,
):
    height, width = (
        values.shape
    )

    driver = (
        gdal.GetDriverByName(
            "GTiff"
        )
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
        srs.ImportFromEPSG(
            4326
        )
        == 0
    )

    dataset.SetProjection(
        srs.ExportToWkt()
    )

    band = (
        dataset.GetRasterBand(1)
    )

    band.WriteArray(
        values
    )

    band.FlushCache()

    dataset.FlushCache()

    dataset = None


def _create_pair(
    tmp_path,
):
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


def _create_task(
    client,
):
    response = client.post(
        "/tasks",
        data={
            "name": (
                "网页 MCD64 测试"
            ),
            "analysis_start": "",
            "analysis_end": "",
            "analysis_scope": (
                "mcd64_only"
            ),
        },
        follow_redirects=False,
    )

    assert (
        response.status_code
        == 302
    )

    location = response.headers[
        "Location"
    ]

    return location.rstrip(
        "/"
    ).split("/")[-1]


def _upload_file(
    client,
    task_id,
    path,
    role,
):
    with path.open(
        "rb"
    ) as handle:
        data = handle.read()

    response = client.post(
        f"/tasks/{task_id}/files",
        data={
            "file_role": role,
            "file": (
                BytesIO(data),
                path.name,
            ),
        },
        content_type=(
            "multipart/form-data"
        ),
        follow_redirects=False,
    )

    assert (
        response.status_code
        == 302
    )


def _prepare_task(
    app,
    tmp_path,
):
    client = app.test_client()

    task_id = _create_task(
        client
    )

    burn_path, qa_path = (
        _create_pair(
            tmp_path
        )
    )

    _upload_file(
        client,
        task_id,
        burn_path,
        "mcd64_burn_date",
    )

    _upload_file(
        client,
        task_id,
        qa_path,
        "mcd64_qa",
    )

    return (
        client,
        task_id,
    )


def test_web_can_execute_standard_mcd64_processing(
    tmp_path,
):
    app = _create_app(
        tmp_path
    )

    _add_region(app)

    client, task_id = (
        _prepare_task(
            app,
            tmp_path,
        )
    )

    response = client.post(
        (
            f"/tasks/{task_id}"
            "/process/mcd64"
        ),
        data={
            "qa_policy": (
                "standard"
            )
        },
        follow_redirects=True,
    )

    assert (
        response.status_code
        == 200
    )

    assert (
        "MCD64A1 处理记录"
        in response.get_data(
            as_text=True
        )
    )

    database = app.extensions[
        "fire_database"
    ]

    with database.connect() as conn:
        pixel_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM burned_pixels
                """
            ).fetchone()[0]
        )

    assert pixel_count == 3

    runs = (
        database.list_import_runs(
            task_id=task_id,
            data_kind=(
                "burned_pixels_tif"
            ),
        )
    )

    assert len(runs) == 1

    report = runs[0][
        "metadata"
    ]

    assert (
        report["qa_policy"]
        == "standard"
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


def test_web_passes_strict_qa_policy(
    tmp_path,
):
    app = _create_app(
        tmp_path
    )

    _add_region(app)

    client, task_id = (
        _prepare_task(
            app,
            tmp_path,
        )
    )

    response = client.post(
        (
            f"/tasks/{task_id}"
            "/process/mcd64"
        ),
        data={
            "qa_policy": (
                "strict"
            )
        },
        follow_redirects=False,
    )

    assert (
        response.status_code
        == 302
    )

    database = app.extensions[
        "fire_database"
    ]

    runs = (
        database.list_import_runs(
            task_id=task_id,
            data_kind=(
                "burned_pixels_tif"
            ),
        )
    )

    assert len(runs) == 1

    report = runs[0][
        "metadata"
    ]

    assert (
        report["qa_policy"]
        == "strict"
    )

    assert (
        report[
            "run_burned_pixel_count"
        ]
        == 2
    )


def test_web_does_not_process_mcd64_without_regions(
    tmp_path,
):
    app = _create_app(
        tmp_path
    )

    client, task_id = (
        _prepare_task(
            app,
            tmp_path,
        )
    )

    response = client.post(
        (
            f"/tasks/{task_id}"
            "/process/mcd64"
        ),
        data={
            "qa_policy": (
                "standard"
            )
        },
        follow_redirects=True,
    )

    assert (
        response.status_code
        == 400
    )

    text = response.get_data(
        as_text=True
    )

    assert (
        "尚未导入行政区边界"
        in text
    )

    database = app.extensions[
        "fire_database"
    ]

    with database.connect() as conn:
        pixel_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM burned_pixels
                """
            ).fetchone()[0]
        )

    assert pixel_count == 0