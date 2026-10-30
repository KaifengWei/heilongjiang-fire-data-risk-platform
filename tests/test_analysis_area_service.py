import pytest

from fire_monitor.services.analysis_area_service import (
    DEFAULT_LABEL, normalize_area_label, parse_request_bbox,
    observation_bbox, within_bbox,
)


def test_area_name_and_bbox_validation():
    assert normalize_area_label("") == DEFAULT_LABEL
    assert normalize_area_label(" 用户关注区域 ") == "用户关注区域"
    assert parse_request_bbox("") is None
    assert parse_request_bbox("110,30,112,32") == [110.0, 30.0, 112.0, 32.0]
    assert within_bbox(111.5, 31.5, [110, 30, 112, 32])
    assert not within_bbox(130, 45, [110, 30, 112, 32])
    for invalid in ("110,30,109,32", "110,30,112", "NaN,30,112,32", "181,30,182,32"):
        with pytest.raises(ValueError):
            parse_request_bbox(invalid)


def test_observed_bbox_is_from_hotspot_points_not_requested_download_bounds():
    assert observation_bbox([{"longitude": 110.5, "latitude": 30.7},
                             {"longitude": 111.3, "latitude": 31.9}]) == [110.5, 30.7, 111.3, 31.9]
    assert observation_bbox([]) is None
