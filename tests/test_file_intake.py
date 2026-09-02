# Day3A：输入文件基础校验、任务隔离存储、SHA256与文件登记测试
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

from fire_monitor.core.file_validation import (
    validate_firms_csv,
)
from fire_monitor.services.task_service import (
    TaskService,
)
from fire_monitor.services.validation_service import (
    ValidationService,
)
from fire_monitor.storage.database import Database

gdal.UseExceptions()

def test_valid_firms_csv(
    tmp_path,
):
    source = tmp_path / "firms.csv"

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "instrument,confidence\n"
            "45.75,126.65,2026-03-15,"
            "VIIRS,n\n"
            "46.10,127.20,2026-03-16,"
            "VIIRS,h\n"
        ),
        encoding="utf-8",
    )

    result = validate_firms_csv(source)

    assert result.status == "valid"
    assert result.accepted is True
    assert result.metadata[
        "total_rows"
    ] == 2
    assert result.metadata[
        "invalid_rows"
    ] == 0


def test_firms_csv_missing_required_column(
    tmp_path,
):
    source = tmp_path / "bad.csv"

    source.write_text(
        (
            "latitude,acq_date\n"
            "45.75,2026-03-15\n"
        ),
        encoding="utf-8",
    )

    result = validate_firms_csv(source)

    assert result.status == "invalid"
    assert result.accepted is False
    assert "longitude" in result.message


def test_firms_csv_warns_about_bad_rows(
    tmp_path,
):
    source = tmp_path / "mixed.csv"

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "instrument,confidence\n"
            "45.75,126.65,2026-03-15,"
            "VIIRS,n\n"
            "999,126.70,2026-03-16,"
            "VIIRS,n\n"
        ),
        encoding="utf-8",
    )

    result = validate_firms_csv(source)

    assert (
        result.status
        == "valid_with_warnings"
    )
    assert result.accepted is True
    assert result.metadata[
        "total_rows"
    ] == 2
    assert result.metadata[
        "invalid_rows"
    ] == 1


def test_firms_csv_without_quality_columns_warns(
    tmp_path,
):
    source = tmp_path / "minimal.csv"

    source.write_text(
        (
            "latitude,longitude,acq_date\n"
            "45.75,126.65,2026-03-15\n"
        ),
        encoding="utf-8",
    )

    result = validate_firms_csv(source)

    assert (
        result.status
        == "valid_with_warnings"
    )
    assert result.accepted is True
    assert "instrument" in result.message
    assert "confidence" in result.message


def test_validation_service_copies_and_registers_file(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    task_service = TaskService(
        database
    )

    task = task_service.create_task(
        "文件接收测试"
    )

    source = tmp_path / "source_firms.csv"

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "instrument,confidence\n"
            "45.75,126.65,2026-03-15,"
            "VIIRS,n\n"
        ),
        encoding="utf-8",
    )

    service = ValidationService(
        database,
        uploads_root=(
            tmp_path / "uploads"
        ),
    )

    record = service.receive_local_file(
        task_id=task["task_id"],
        source_path=source,
        file_role="firms_csv",
        source_agency="NASA FIRMS",
        product_name="VIIRS",
        processing_class="TEST",
    )

    assert record[
        "validation_status"
    ] == "valid"

    assert record["sha256"]

    stored_path = Path(
        record["stored_path"]
    )

    assert stored_path.is_file()

    assert stored_path.parent.name == (
        task["task_id"]
    )

    assert (
        stored_path.read_bytes()
        == source.read_bytes()
    )


def test_same_file_is_not_registered_twice(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    task_service = TaskService(
        database
    )

    task = task_service.create_task(
        "重复文件测试"
    )

    source = tmp_path / "firms.csv"

    source.write_text(
        (
            "latitude,longitude,acq_date,"
            "instrument,confidence\n"
            "45.75,126.65,2026-03-15,"
            "VIIRS,n\n"
        ),
        encoding="utf-8",
    )

    service = ValidationService(
        database,
        uploads_root=(
            tmp_path / "uploads"
        ),
    )

    first = service.receive_local_file(
        task_id=task["task_id"],
        source_path=source,
        file_role="firms_csv",
    )

    second = service.receive_local_file(
        task_id=task["task_id"],
        source_path=source,
        file_role="firms_csv",
    )

    assert first["id"] == second["id"]

    files = database.list_input_files(
        task["task_id"]
    )

    assert len(files) == 1


def test_unknown_file_role_is_rejected(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    task_service = TaskService(
        database
    )

    task = task_service.create_task(
        "非法类型测试"
    )

    source = tmp_path / "test.txt"
    source.write_text(
        "hello",
        encoding="utf-8",
    )

    service = ValidationService(
        database,
        uploads_root=(
            tmp_path / "uploads"
        ),
    )

    with pytest.raises(ValueError):
        service.receive_local_file(
            task_id=task["task_id"],
            source_path=source,
            file_role="unknown",
        )

def _create_test_mcd64_geotiff(
    path: Path,
) -> None:
    """创建文件接收测试使用的小型 GeoTIFF。"""

    driver = gdal.GetDriverByName(
        "GTiff"
    )

    dataset = driver.Create(
        str(path),
        3,
        2,
        1,
        gdal.GDT_Int16,
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
    assert srs.ImportFromEPSG(4326) == 0

    dataset.SetProjection(
        srs.ExportToWkt()
    )

    band = dataset.GetRasterBand(1)

    band.WriteArray(
        np.full(
            (2, 3),
            60,
            dtype=np.int16,
        )
    )

    band.FlushCache()
    dataset.FlushCache()

    dataset = None

def test_mcd64_intake_preserves_product_date(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    task_service = TaskService(
        database
    )

    task = task_service.create_task(
        "MCD64 文件接收测试"
    )

    source = (
        tmp_path
        / "MCD64A1.A2026060.burndate.tif"
    )

    _create_test_mcd64_geotiff(
        source
    )

    service = ValidationService(
        database,
        uploads_root=(
            tmp_path / "uploads"
        ),
    )

    record = service.receive_local_file(
        task_id=task["task_id"],
        source_path=source,
        file_role="mcd64_burn_date",
        source_agency="test_fixture",
        product_name="MCD64A1",
    )

    assert (
        record["validation_status"]
        == "valid"
    )

    stored_path = Path(
        record["stored_path"]
    )

    assert stored_path.is_file()

    assert "A2026060" in (
        stored_path.name
    )

    validation_metadata = (
        record["metadata"]["validation"]
    )

    assert (
        validation_metadata["year"]
        == 2026
    )

    assert (
        validation_metadata[
            "month_start_doy"
        ]
        == 60
    )