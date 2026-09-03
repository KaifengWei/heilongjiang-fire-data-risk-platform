# Day5B：MCD64A1 Burn Date结合QA筛选、行政区落区与面积计算测试

from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from fire_monitor.core.geography import (
    RegionIndex,
)
from fire_monitor.core.mcd64 import (
    extract_mcd64_burned_pixels,
)


gdal.UseExceptions()


def _create_geotiff(
    path: Path,
    values: np.ndarray,
    *,
    data_type: int,
) -> None:
    height, width = values.shape

    driver = gdal.GetDriverByName(
        "GTiff"
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
        srs.ImportFromEPSG(4326)
        == 0
    )

    dataset.SetProjection(
        srs.ExportToWkt()
    )

    band = dataset.GetRasterBand(1)

    band.WriteArray(
        values
    )

    band.FlushCache()
    dataset.FlushCache()

    dataset = None


def _region_index() -> RegionIndex:
    return RegionIndex(
        [
            {
                "name": "测试区域",
                "level": "city",
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
                "source": "test",
                "version": "1",
            }
        ]
    )


def _create_pair(
    tmp_path,
) -> tuple[
    Path,
    Path,
]:
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
            # 3: clean
            # 7: shortened
            # 0: water + invalid
            [3, 7, 0, 3],

            # 35: special condition
            # 3: outside-month Burn Date
            # 11: contextual relabeling
            # 3: outside configured region
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


def test_standard_qa_filters_burned_pixels(
    tmp_path,
):
    (
        burn_path,
        qa_path,
    ) = _create_pair(
        tmp_path
    )

    rows, report = (
        extract_mcd64_burned_pixels(
            burn_path,
            qa_path=qa_path,
            region_index=(
                _region_index()
            ),
            qa_policy="standard",
        )
    )

    # Burn Date > 0：
    # 7 个候选像元
    assert (
        report[
            "positive_burn_date_pixels"
        ]
        == 7
    )

    # DOY 91 不属于 2026 年 3 月
    assert (
        report[
            "positive_values_outside_expected_month"
        ]
        == 1
    )

    # 剩余 6 个进入 QA 判断
    assert (
        report[
            "qa_evaluated_pixels"
        ]
        == 6
    )

    # QA=0、QA=35 两个被拒绝
    assert (
        report[
            "qa_rejected_pixels"
        ]
        == 2
    )

    assert (
        report[
            "qa_rejection_counts"
        ]["water"]
        == 1
    )

    assert (
        report[
            "qa_rejection_counts"
        ][
            "insufficient_valid_data"
        ]
        == 1
    )

    assert (
        report[
            "qa_rejection_counts"
        ][
            "special_condition"
        ]
        == 1
    )

    # standard 不删除 shortened
    assert (
        report[
            "qa_shortened_mapping_period_pixels"
        ]
        == 1
    )

    assert (
        report[
            "qa_contextually_relabeled_pixels"
        ]
        == 1
    )

    # 一个通过 QA 的像元在行政区外
    assert (
        report[
            "outside_configured_regions"
        ]
        == 1
    )

    assert (
        report[
            "accepted_burned_pixels"
        ]
        == 3
    )

    assert len(rows) == 3

    assert (
        report[
            "accepted_burned_area_km2"
        ]
        > 0
    )

    assert {
        row["doy"]
        for row in rows
    } == {
        60,
        61,
        64,
    }


def test_strict_qa_removes_shortened_mapping_pixel(
    tmp_path,
):
    (
        burn_path,
        qa_path,
    ) = _create_pair(
        tmp_path
    )

    rows, report = (
        extract_mcd64_burned_pixels(
            burn_path,
            qa_path=qa_path,
            region_index=(
                _region_index()
            ),
            qa_policy="strict",
        )
    )

    assert (
        report[
            "qa_rejected_pixels"
        ]
        == 3
    )

    assert (
        report[
            "qa_rejection_counts"
        ][
            "shortened_mapping_period"
        ]
        == 1
    )

    assert (
        report[
            "accepted_burned_pixels"
        ]
        == 2
    )

    assert {
        row["doy"]
        for row in rows
    } == {
        60,
        64,
    }


def test_legacy_extraction_without_qa_still_works(
    tmp_path,
):
    burn_path, _ = (
        _create_pair(
            tmp_path
        )
    )

    rows, report = (
        extract_mcd64_burned_pixels(
            burn_path,
            region_index=(
                _region_index()
            ),
        )
    )

    assert (
        report["qa_available"]
        is False
    )

    assert (
        report["qa_applied"]
        is False
    )

    assert (
        report[
            "qa_evaluated_pixels"
        ]
        == 0
    )

    # 没有 QA 时：
    # 只进行月份检查和行政区落区。
    assert (
        report[
            "accepted_burned_pixels"
        ]
        == 5
    )

    assert len(rows) == 5