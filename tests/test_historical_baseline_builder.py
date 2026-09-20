from __future__ import annotations

import json

import pandas as pd

from fire_monitor.services.historical_baseline_service import (
    HistoricalFirmsBaselineBuilder,
)


def test_builder_uses_only_noaa20_science_quality_rows(tmp_path):
    geojson = tmp_path / "regions.geojson"
    geojson.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "测试市"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [125.0, 44.0],
                                    [127.0, 44.0],
                                    [127.0, 46.0],
                                    [125.0, 46.0],
                                    [125.0, 44.0],
                                ]
                            ],
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    csv_path = tmp_path / "archive.csv"

    pd.DataFrame(
        [
            {
                "latitude": 45.0,
                "longitude": 126.0,
                "acq_date": "2019-04-01",
                "acq_time": "0300",
                "instrument": "VIIRS",
                "satellite": "N20",
                "confidence": "n",
                "version": "2.0",
                "frp": 10.0,
            },
            {
                "latitude": 45.1,
                "longitude": 126.1,
                "acq_date": "2019-04-01",
                "acq_time": "0310",
                "instrument": "VIIRS",
                "satellite": "N21",
                "confidence": "n",
                "version": "2.0",
                "frp": 11.0,
            },
            {
                "latitude": 45.2,
                "longitude": 126.2,
                "acq_date": "2019-04-01",
                "acq_time": "0320",
                "instrument": "VIIRS",
                "satellite": "N20",
                "confidence": "n",
                "version": "2.0NRT",
                "frp": 12.0,
            },
        ]
    ).to_csv(csv_path, index=False)

    output = tmp_path / "baseline.json"

    payload = HistoricalFirmsBaselineBuilder(
        region_geojson_path=geojson,
        expected_years=[2019],
    ).build(
        [csv_path],
        output_path=output,
    )

    assert payload["daily"]["2019-04-01"]["total"] == 1
    assert payload["daily"]["2019-04-01"]["regions"]["测试市"] == 1
    assert payload["report"]["non_noaa20_rows"] == 1
    assert payload["report"]["non_science_quality_rows"] == 1
