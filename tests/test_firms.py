# 原有的FIRMS质量规则、基础规范化及API日期分段测试

import pandas as pd

from fire_monitor.core.firms import firms_quality_pass, normalized_firms_rows, split_firms_date_ranges


def test_firms_quality_rule():
    assert firms_quality_pass("VIIRS", "n")
    assert firms_quality_pass("VIIRS", "h")
    assert not firms_quality_pass("VIIRS", "l")
    assert firms_quality_pass("MODIS", 30)
    assert not firms_quality_pass("MODIS", 29)
    assert not firms_quality_pass("unknown", "h")


def test_normalized_rows_apply_quality_filter():
    frame = pd.DataFrame(
        [
            {"latitude": 45.1, "longitude": 126.1, "acq_date": "2026-03-01", "instrument": "VIIRS", "confidence": "n"},
            {"latitude": 45.2, "longitude": 126.2, "acq_date": "2026-03-01", "instrument": "VIIRS", "confidence": "l"},
            {"latitude": 45.3, "longitude": 126.3, "acq_date": "2026-03-01", "instrument": "MODIS", "confidence": 30},
            {"latitude": 45.4, "longitude": 126.4, "acq_date": "2026-03-01", "instrument": "MODIS", "confidence": 29},
        ]
    )
    rows = list(normalized_firms_rows(frame, firms_source="test", quality_only=True))
    assert len(rows) == 2
    assert {row["instrument"] for row in rows} == {"VIIRS", "MODIS"}
    assert all(row["quality_rule"] for row in rows)


def test_firms_date_range_is_split_to_at_most_five_days():
    blocks = list(split_firms_date_ranges(pd.Timestamp("2026-03-01").date(), pd.Timestamp("2026-03-12").date()))
    assert [days for _, days in blocks] == [5, 5, 2]
    assert blocks[0][0].isoformat() == "2026-03-01"
    assert blocks[-1][0].isoformat() == "2026-03-11"
