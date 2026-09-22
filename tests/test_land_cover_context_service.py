from __future__ import annotations

import numpy as np
import pytest

gdal = pytest.importorskip("osgeo.gdal")
osr = pytest.importorskip("osgeo.osr")

from fire_monitor.services.land_cover_context_service import (
    LandCoverContextService,
)


def _write_raster(path):
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(
        str(path),
        4,
        2,
        1,
        gdal.GDT_Byte,
    )
    dataset.SetGeoTransform(
        (120.0, 1.0, 0.0, 50.0, 0.0, -1.0)
    )

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dataset.SetProjection(srs.ExportToWkt())

    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(255)
    band.WriteArray(
        np.array(
            [
                [12, 12, 1, 1],
                [14, 10, 13, 17],
            ],
            dtype=np.uint8,
        )
    )
    dataset = None


def test_land_cover_context_identifies_agricultural_background(tmp_path):
    raster = tmp_path / "lc.tif"
    _write_raster(raster)

    rows = [
        {"longitude": 120.5, "latitude": 49.5, "region_name": "佳木斯市"},
        {"longitude": 121.5, "latitude": 49.5, "region_name": "佳木斯市"},
        {"longitude": 120.5, "latitude": 48.5, "region_name": "佳木斯市"},
        {"longitude": 122.5, "latitude": 49.5, "region_name": "大兴安岭地区"},
    ]

    result = LandCoverContextService(
        raster,
        minimum_coverage=0.5,
    ).analyze(rows)

    assert result["available"] is True
    assert result["dominant_group"] == "agriculture"
    assert "农田" in result["guidance"]
    assert (
        result["regions"]["佳木斯市"]["dominant_group"]
        == "agriculture"
    )


def test_land_cover_context_returns_unavailable_when_raster_missing(tmp_path):
    result = LandCoverContextService(
        tmp_path / "missing.tif"
    ).analyze(
        [
            {
                "longitude": 126.0,
                "latitude": 45.0,
                "region_name": "哈尔滨市",
            }
        ]
    )

    assert result["available"] is False
    assert result["reason"] == "land_cover_not_installed"


def test_land_cover_context_uses_mixed_message_when_no_type_dominates(tmp_path):
    raster = tmp_path / "lc.tif"
    _write_raster(raster)

    rows = [
        {"longitude": 120.5, "latitude": 49.5, "region_name": "测试市"},
        {"longitude": 122.5, "latitude": 49.5, "region_name": "测试市"},
        {"longitude": 123.5, "latitude": 48.5, "region_name": "测试市"},
    ]

    result = LandCoverContextService(
        raster,
        minimum_coverage=0.5,
    ).analyze(rows)

    assert result["available"] is True
    assert result["dominant_group"] == "mixed"
    assert "多种地表类型" in result["guidance"]

def test_priority_guidance_combines_history_regions_with_land_cover(tmp_path):
    raster = tmp_path / "lc.tif"
    _write_raster(raster)

    service = LandCoverContextService(
        raster,
        minimum_coverage=0.5,
    )

    analysis = service.analyze(
        [
            {"longitude": 120.5, "latitude": 49.5, "region_name": "佳木斯市"},
            {"longitude": 121.5, "latitude": 49.5, "region_name": "佳木斯市"},
            {"longitude": 120.5, "latitude": 48.5, "region_name": "双鸭山市"},
        ]
    )

    guidance = service.build_priority_guidance(
        analysis,
        [
            {"region_name": "佳木斯市"},
            {"region_name": "双鸭山市"},
        ],
    )

    assert guidance is not None
    assert guidance["common_group"] == "agriculture"
    assert "农田背景区域" in guidance["message"]
    assert guidance["items"][0]["dominant_label"] == "农田背景"
