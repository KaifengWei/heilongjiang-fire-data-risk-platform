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


def test_multiple_nonadjacent_areas_are_grid_groups_not_city_names():
    from fire_monitor.services.analysis_area_service import group_observations_by_grid
    result = group_observations_by_grid([
        {"longitude": 126.65, "latitude": 45.75},
        {"longitude": 126.75, "latitude": 45.83},
        {"longitude": 123.5, "latitude": 47.2},
        {"longitude": "not-a-number", "latitude": "42"},
    ])
    assert result["total"] == 3
    assert result["cell_count"] == 2
    assert [row["count"] for row in result["groups"]] == [2, 1]
    assert "经度 126" in result["groups"][0]["label"]
    assert "行政区" in result["note"]


def test_grid_group_limit_keeps_remainder_and_negative_coords():
    from fire_monitor.services.analysis_area_service import group_observations_by_grid
    result = group_observations_by_grid([
        {"longitude": -0.2, "latitude": 20.5},
        {"longitude": -1.2, "latitude": 20.5},
        {"longitude": -2.2, "latitude": 20.5},
    ], max_groups=2)
    assert result["cell_count"] == 3
    assert result["total"] == 3
    assert result["other_count"] == 1
