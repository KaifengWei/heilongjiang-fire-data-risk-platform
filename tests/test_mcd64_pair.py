# Day3B：MCD64A1 Burn Date与QA GeoTIFF配对一致性测试

from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from fire_monitor.core.mcd64_validation import (
    validate_mcd64_pair,
)


gdal.UseExceptions()


def _create_test_geotiff(
    path: Path,
    *,
    width: int = 4,
    height: int = 3,
    geotransform: tuple[
        float,
        float,
        float,
        float,
        float,
        float,
    ] = (
        125.0,
        0.01,
        0.0,
        48.0,
        0.0,
        -0.01,
    ),
    epsg: int = 4326,
    data_type: int = gdal.GDT_Int16,
    fill_value: int = 60,
) -> None:
    """创建用于自动测试的小型真实 GeoTIFF。"""

    driver = gdal.GetDriverByName("GTiff")

    dataset = driver.Create(
        str(path),
        width,
        height,
        1,
        data_type,
    )

    assert dataset is not None

    dataset.SetGeoTransform(
        geotransform
    )

    srs = osr.SpatialReference()
    assert srs.ImportFromEPSG(epsg) == 0

    dataset.SetProjection(
        srs.ExportToWkt()
    )

    array = np.full(
        (height, width),
        fill_value,
        dtype=np.int16,
    )

    band = dataset.GetRasterBand(1)
    band.WriteArray(array)
    band.FlushCache()

    dataset.FlushCache()
    dataset = None


def test_valid_mcd64_pair(
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

    _create_test_geotiff(
        burn_path,
        data_type=gdal.GDT_Int16,
        fill_value=60,
    )

    _create_test_geotiff(
        qa_path,
        data_type=gdal.GDT_Byte,
        fill_value=3,
    )

    result = validate_mcd64_pair(
        burn_path,
        qa_path,
    )

    assert result.status == "valid"
    assert result.accepted is True
    assert result.metadata["width"] == 4
    assert result.metadata["height"] == 3
    assert result.metadata["crs"] == (
        "EPSG:4326"
    )

    assert result.metadata[
        "pixel_size"
    ] == {
        "x": 0.01,
        "y": 0.01,
    }


def test_mcd64_pair_rejects_size_mismatch(
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

    _create_test_geotiff(
        burn_path,
        width=4,
        height=3,
    )

    _create_test_geotiff(
        qa_path,
        width=5,
        height=3,
        data_type=gdal.GDT_Byte,
        fill_value=3,
    )

    result = validate_mcd64_pair(
        burn_path,
        qa_path,
    )

    assert result.status == "invalid"
    assert "尺寸" in result.message


def test_mcd64_pair_rejects_geotransform_mismatch(
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

    _create_test_geotiff(
        burn_path,
    )

    _create_test_geotiff(
        qa_path,
        geotransform=(
            125.01,
            0.01,
            0.0,
            48.0,
            0.0,
            -0.01,
        ),
        data_type=gdal.GDT_Byte,
        fill_value=3,
    )

    result = validate_mcd64_pair(
        burn_path,
        qa_path,
    )

    assert result.status == "invalid"
    assert "GeoTransform" in result.message


def test_mcd64_pair_rejects_product_date_mismatch(
    tmp_path,
):
    burn_path = (
        tmp_path
        / "MCD64A1.A2026060.burndate.tif"
    )

    qa_path = (
        tmp_path
        / "MCD64A1.A2026091.qa.tif"
    )

    _create_test_geotiff(
        burn_path,
    )

    _create_test_geotiff(
        qa_path,
        data_type=gdal.GDT_Byte,
        fill_value=3,
    )

    result = validate_mcd64_pair(
        burn_path,
        qa_path,
    )

    assert result.status == "invalid"
    assert "AYYYYDDD" in result.message


def test_mcd64_pair_rejects_wrong_crs(
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

    _create_test_geotiff(
        burn_path,
    )

    _create_test_geotiff(
        qa_path,
        epsg=3857,
        data_type=gdal.GDT_Byte,
        fill_value=3,
    )

    result = validate_mcd64_pair(
        burn_path,
        qa_path,
    )

    assert result.status == "invalid"
    assert "QA 文件基础校验失败" in (
        result.message
    )

def test_mcd64_pair_rejects_unreadable_geotiff(
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

    burn_path.write_text(
        "this is not a geotiff",
        encoding="utf-8",
    )

    _create_test_geotiff(
        qa_path,
        data_type=gdal.GDT_Byte,
        fill_value=3,
    )

    result = validate_mcd64_pair(
        burn_path,
        qa_path,
    )

    assert result.status == "invalid"
    assert "Burn Date 文件基础校验失败" in (
        result.message
    )
    assert "GDAL 无法打开" in result.message