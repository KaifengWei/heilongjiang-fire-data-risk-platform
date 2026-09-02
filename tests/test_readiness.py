# Day3C：firms_only、mcd64_only与combined任务输入准备状态测试
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from fire_monitor.services.readiness_service import (
    ReadinessService,
)
from fire_monitor.services.task_service import (
    TaskService,
)
from fire_monitor.services.validation_service import (
    ValidationService,
)
from fire_monitor.storage.database import Database


gdal.UseExceptions()


def _create_geotiff(
    path: Path,
    *,
    geotransform=(
        125.0,
        0.01,
        0.0,
        48.0,
        0.0,
        -0.01,
    ),
    fill_value: int = 60,
    data_type: int = gdal.GDT_Int16,
) -> None:
    driver = gdal.GetDriverByName(
        "GTiff"
    )

    dataset = driver.Create(
        str(path),
        3,
        2,
        1,
        data_type,
    )

    assert dataset is not None

    dataset.SetGeoTransform(
        geotransform
    )

    srs = osr.SpatialReference()
    assert srs.ImportFromEPSG(4326) == 0

    dataset.SetProjection(
        srs.ExportToWkt()
    )

    array = np.full(
        (2, 3),
        fill_value,
        dtype=np.int16,
    )

    band = dataset.GetRasterBand(1)
    band.WriteArray(array)
    band.FlushCache()

    dataset.FlushCache()
    dataset = None


def _create_valid_firms(
    path: Path,
) -> None:
    path.write_text(
        (
            "latitude,longitude,acq_date,"
            "instrument,confidence\n"
            "45.75,126.65,2026-03-15,"
            "VIIRS,n\n"
        ),
        encoding="utf-8",
    )


def _services(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

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

    readiness_service = (
        ReadinessService(database)
    )

    return (
        database,
        task_service,
        validation_service,
        readiness_service,
    )


def test_empty_combined_task_is_not_ready(
    tmp_path,
):
    (
        _database,
        task_service,
        _validation,
        readiness,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "空任务",
        parameters={
            "analysis_scope": "combined",
        },
    )

    result = readiness.evaluate_task(
        task["task_id"]
    )

    assert result.ready is False
    assert result.status == "not_ready"

    assert any(
        "FIRMS" in reason
        for reason in result.reasons
    )

    assert any(
        "Burn Date" in reason
        for reason in result.reasons
    )

    assert any(
        "QA" in reason
        for reason in result.reasons
    )


def test_firms_only_task_can_be_ready(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        readiness,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "FIRMS 单独分析",
        parameters={
            "analysis_scope": "firms_only",
        },
    )

    source = tmp_path / "firms.csv"
    _create_valid_firms(source)

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=source,
        file_role="firms_csv",
    )

    result = (
        readiness
        .evaluate_and_sync_status(
            task["task_id"]
        )
    )

    assert result.ready is True
    assert result.reasons == []

    stored_task = (
        database.get_analysis_task(
            task["task_id"]
        )
    )

    assert stored_task is not None
    assert stored_task["status"] == "ready"


def test_combined_task_can_be_ready(
    tmp_path,
):
    (
        database,
        task_service,
        validation,
        readiness,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "联合分析",
        parameters={
            "analysis_scope": "combined",
        },
    )

    firms_path = (
        tmp_path / "firms.csv"
    )

    burn_path = (
        tmp_path
        / "MCD64A1.A2026060.burndate.tif"
    )

    qa_path = (
        tmp_path
        / "MCD64A1.A2026060.qa.tif"
    )

    _create_valid_firms(
        firms_path
    )

    _create_geotiff(
        burn_path,
        fill_value=60,
        data_type=gdal.GDT_Int16,
    )

    _create_geotiff(
        qa_path,
        fill_value=3,
        data_type=gdal.GDT_Byte,
    )

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=firms_path,
        file_role="firms_csv",
    )

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=burn_path,
        file_role="mcd64_burn_date",
    )

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=qa_path,
        file_role="mcd64_qa",
    )

    result = (
        readiness
        .evaluate_and_sync_status(
            task["task_id"]
        )
    )

    assert result.ready is True
    assert result.reasons == []

    assert len(
        result.details["mcd64_pairs"]
    ) == 1

    assert (
        result.details[
            "mcd64_pairs"
        ][0]["product_date"]
        == "A2026060"
    )

    stored_task = (
        database.get_analysis_task(
            task["task_id"]
        )
    )

    assert stored_task is not None
    assert stored_task["status"] == "ready"


def test_mcd64_missing_matching_qa_is_not_ready(
    tmp_path,
):
    (
        _database,
        task_service,
        validation,
        readiness,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "缺少 QA",
        parameters={
            "analysis_scope": "mcd64_only",
        },
    )

    burn_path = (
        tmp_path
        / "MCD64A1.A2026060.burndate.tif"
    )

    _create_geotiff(
        burn_path
    )

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=burn_path,
        file_role="mcd64_burn_date",
    )

    result = readiness.evaluate_task(
        task["task_id"]
    )

    assert result.ready is False

    assert any(
        "QA" in reason
        for reason in result.reasons
    )


def test_mcd64_different_product_dates_are_not_ready(
    tmp_path,
):
    (
        _database,
        task_service,
        validation,
        readiness,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "月份不匹配",
        parameters={
            "analysis_scope": "mcd64_only",
        },
    )

    burn_path = (
        tmp_path
        / "MCD64A1.A2026060.burndate.tif"
    )

    qa_path = (
        tmp_path
        / "MCD64A1.A2026091.qa.tif"
    )

    _create_geotiff(
        burn_path
    )

    _create_geotiff(
        qa_path,
        fill_value=3,
        data_type=gdal.GDT_Byte,
    )

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=burn_path,
        file_role="mcd64_burn_date",
    )

    validation.receive_local_file(
        task_id=task["task_id"],
        source_path=qa_path,
        file_role="mcd64_qa",
    )

    result = readiness.evaluate_task(
        task["task_id"]
    )

    assert result.ready is False

    assert any(
        "缺少对应" in reason
        for reason in result.reasons
    )


def test_firms_warning_does_not_block_firms_only_task(
    tmp_path,
):
    (
        _database,
        task_service,
        validation,
        readiness,
    ) = _services(tmp_path)

    task = task_service.create_task(
        "FIRMS 警告任务",
        parameters={
            "analysis_scope": "firms_only",
        },
    )

    firms_path = (
        tmp_path / "minimal.csv"
    )

    firms_path.write_text(
        (
            "latitude,longitude,acq_date\n"
            "45.75,126.65,2026-03-15\n"
        ),
        encoding="utf-8",
    )

    record = (
        validation.receive_local_file(
            task_id=task["task_id"],
            source_path=firms_path,
            file_role="firms_csv",
        )
    )

    assert (
        record["validation_status"]
        == "valid_with_warnings"
    )

    result = readiness.evaluate_task(
        task["task_id"]
    )

    assert result.ready is True
    assert result.warnings