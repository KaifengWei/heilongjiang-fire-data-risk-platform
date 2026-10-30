"""Agricultural relevance checks with controlled MCD12Q1 test rasters."""
import numpy as np
import pytest

gdal = pytest.importorskip("osgeo.gdal")
osr = pytest.importorskip("osgeo.osr")

from fire_monitor.services.land_cover_context_service import LandCoverContextService
from fire_monitor.services.agricultural_relevance_service import (
    AgriculturalRelevanceService, validate_calendar_rules,
)
from fire_monitor.services.crop_calendar_store import CropCalendarStore


def raster(path):
    ds = gdal.GetDriverByName("GTiff").Create(str(path), 4, 1, 1, gdal.GDT_Byte)
    ds.SetGeoTransform((110, 1, 0, 40, 0, -1))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(255)
    ds.GetRasterBand(1).WriteArray(np.array([[12, 14, 1, 255]], dtype=np.uint8))
    ds = None


def obs(lon, *, region="示例市", date="2026-10-12"):
    return {
        "longitude": lon, "latitude": 39.5,
        "region_name": region, "acquired_date": date,
        "confidence": "n", "frp": 8.0,
    }


def configured():
    return [{"region_name": "示例市", "crop": "示例作物", "months": [10, 11],
             "source": "测试用农事时历，不代表实际播收时间"}]


def test_cropland_with_provenance_calendar_is_more_relevant(tmp_path):
    f = tmp_path / "lc.tif"
    raster(f)
    result = AgriculturalRelevanceService(LandCoverContextService(f)).analyze(
        [obs(110.5), obs(111.5), obs(112.5), obs(113.5)],
        calendar_rules=configured(),
    )
    assert result["counts"] == {
        "较高相关": 1, "可能相关": 1, "较低相关": 1, "证据不足": 1,
    }
    assert result["examples"][0]["land_cover_class"] == 12
    assert result["examples"][1]["land_cover_class"] == 14
    assert result["land_cover_matched"] == 3


def test_missing_calendar_and_out_of_season_do_not_become_high_relevance(tmp_path):
    f = tmp_path / "lc.tif"
    raster(f)
    service = AgriculturalRelevanceService(LandCoverContextService(f))
    no_calendar = service.analyze([obs(110.5)])
    assert no_calendar["counts"]["可能相关"] == 1
    assert no_calendar["calendar_states"]["not_configured"] == 1
    other_month = service.analyze([obs(110.5, date="2026-02-01")], calendar_rules=configured())
    assert other_month["counts"]["较低相关"] == 1


def test_uncovered_region_is_not_assumed_cropland_and_multiregion_kept(tmp_path):
    f = tmp_path / "lc.tif"
    raster(f)
    result = AgriculturalRelevanceService(LandCoverContextService(f)).analyze(
        [obs(110.5), obs(130.5, region="另一区")], calendar_rules=configured()
    )
    assert set(result["regions"]) == {"示例市", "另一区"}
    assert result["regions"]["另一区"]["counts"]["证据不足"] == 1
    assert result["land_cover_coverage"] == 0.5


def test_missing_raster_and_invalid_rules_fail_safe(tmp_path):
    service = AgriculturalRelevanceService(LandCoverContextService(tmp_path / "missing.tif"))
    result = service.analyze([obs(110.5)], calendar_rules=configured())
    assert result["land_cover_available"] is False
    assert result["counts"]["证据不足"] == 1
    with pytest.raises(ValueError, match="月份"):
        validate_calendar_rules([{"region_name": "甲", "crop": "乙", "source": "测试来源有效", "months": [0]}])


def test_calendar_store_is_persistent_and_rejects_unsourced_rules(tmp_path):
    store = CropCalendarStore(tmp_path / "config" / "rules.json")
    assert store.load_rules() == []
    import json
    source = {"schema_version": 1, "rules": configured()}
    assert store.import_json(json.dumps(source).encode()) == 1
    assert CropCalendarStore(store.path).load_rules() == configured()
    old_bytes = store.path.read_bytes()
    source["rules"][0]["source"] = ""
    with pytest.raises(ValueError, match="来源"):
        store.import_json(json.dumps(source).encode())
    assert store.path.read_bytes() == old_bytes
