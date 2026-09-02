# 原有的数据库导入、查询、地图数据、CSV导出及空数据首页测试
import json

import pandas as pd

from fire_monitor.app import create_app
from fire_monitor.services.import_service import ImportService
from fire_monitor.storage.database import Database


def create_square_geojson(path):
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"CITY": "测试市"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[120, 40], [130, 40], [130, 50], [120, 50], [120, 40]]],
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_import_query_map_and_export(tmp_path):
    db_path = tmp_path / "fire.sqlite"
    boundary_path = tmp_path / "boundary.geojson"
    create_square_geojson(boundary_path)
    service = ImportService(Database(db_path))
    region_result = service.import_regions(boundary_path, name_field="CITY", source="fixture")
    assert region_result["stored_regions"] == 1

    firms = pd.DataFrame(
        [
            {
                "latitude": 45.0,
                "longitude": 126.0,
                "acq_date": "2026-03-01",
                "acq_time": "0430",
                "instrument": "VIIRS",
                "satellite": "NPP",
                "confidence": "n",
                "frp": 4.2,
            },
            {
                "latitude": 45.0,
                "longitude": 126.0,
                "acq_date": "2026-03-01",
                "instrument": "VIIRS",
                "confidence": "l",
            },
        ]
    )
    result = service.import_firms_dataframe(firms, firms_source="FIRMS_TEST", source_ref="fixture")
    assert result["stored_rows"] == 1

    burned_path = tmp_path / "burned.csv"
    pd.DataFrame(
        [
            {
                "城市": "测试市",
                "日期": "2026-03-01",
                "年积日DOY": 60,
                "经度": 126.0,
                "纬度": 45.0,
                "当前经纬网格面积_km2": 0.17,
            }
        ]
    ).to_csv(burned_path, index=False, encoding="utf-8-sig")
    burned_result = service.import_existing_burned_pixel_csv(burned_path, source_product="MCD64 fixture")
    assert burned_result["stored_rows"] == 1

    client = create_app(db_path, testing=True).test_client()
    summary = client.get("/api/summary?region=测试市&start=2026-03-01&end=2026-03-01").get_json()
    assert summary["active_fire_observation_count"] == 1
    assert summary["burned_pixel_count"] == 1
    assert summary["burned_area_km2"] == 0.17

    map_payload = client.get("/api/map?region=测试市&limit=20").get_json()
    assert map_payload["active_fire"]["total"] == 1
    assert map_payload["burned_pixels"]["total"] == 1
    assert len(map_payload["boundary"]["features"]) == 1

    export = client.get("/api/export.csv?region=测试市")
    assert export.status_code == 200
    assert "主动火点观测记录数" in export.get_data(as_text=True)


def test_index_page_loads_with_no_data(tmp_path):
    client = create_app(tmp_path / "empty.sqlite", testing=True).test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "黑龙江省火点数据检测与风险评估平台" in response.get_data(as_text=True)
