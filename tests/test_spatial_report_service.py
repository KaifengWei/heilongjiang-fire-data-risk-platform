"""Report geometry must match installed WGS84 boundaries and FIRMS points."""

import struct

from fire_monitor.services.spatial_report_service import (
    build_spatial_report_context, display_place,
)


def _poly(name, west, south, east, north):
    return {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {"type": "Polygon", "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south],
        ]]},
    }


def test_matching_is_based_on_true_polygon_not_name_or_bbox():
    areas = [_poly("Jilin Province", 123, 44, 126, 46),
             _poly("Liaoning Province", 120, 40, 123, 43)]
    points = [
        {"longitude": 124.125, "latitude": 45.125},
        {"longitude": 124.18, "latitude": 45.18},
        {"longitude": 121, "latitude": 41},
        {"longitude": 127, "latitude": 45},
    ]
    spatial = build_spatial_report_context(points, areas, source="测试 geoBoundaries")
    assert spatial["total"] == 4
    assert spatial["bbox"] == [121, 41, 127, 45.18]
    assert spatial["matched"] == 3
    assert spatial["outside"] == 1
    assert spatial["ambiguous"] == 0
    assert spatial["regions"] == [
        {"name": "吉林", "count": 2, "share_percent": 50.0},
        {"name": "辽宁", "count": 1, "share_percent": 25.0},
    ]
    assert spatial["focus_grid"]["count"] == 2
    png = spatial["map_png"]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (900, 500)


def test_no_installed_map_still_produces_real_coordinate_plot():
    rows = [{"longitude": 125., "latitude": 45.}]
    spatial = build_spatial_report_context(rows, [])
    assert spatial["has_geographic_background"] is False
    assert spatial["outside"] == 1
    assert spatial["regions"] == []
    assert spatial["map_png"].startswith(b"\x89PNG")


def test_overlap_is_not_double_counted_and_invalid_rows_are_excluded():
    polygon = _poly("Jilin Province", 123, 44, 126, 46)
    spatial = build_spatial_report_context(
        [{"longitude": 124, "latitude": 45}, {"longitude": "x", "latitude": 45}],
        [polygon, polygon],
    )
    assert spatial["total"] == 1
    assert spatial["ambiguous"] == 1
    assert spatial["matched"] == 0


def test_empty_observations_has_no_map():
    assert build_spatial_report_context([], []).get("available") is False
    assert display_place("Unknown Farm Region") == "Unknown Farm Region"
