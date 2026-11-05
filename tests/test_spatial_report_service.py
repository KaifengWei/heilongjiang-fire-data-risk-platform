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



def test_spatial_hotspot_rankings_use_task_dates_and_total_counts():
    sample = [
        {"longitude": 124.12, "latitude": 45.12, "acquired_date": "2026-04-01"},
        {"longitude": 124.16, "latitude": 45.16, "acquired_date": "2026-04-01"},
        {"longitude": 124.13, "latitude": 45.13, "acquired_date": "2026-04-04"},
        {"longitude": 124.35, "latitude": 45.12, "acquired_date": "2026-04-02"},
        {"longitude": 124.36, "latitude": 45.14, "acquired_date": "2026-04-05"},
        {"longitude": 125.35, "latitude": 44.7, "acquired_date": "2026-04-06"},
    ]
    data = build_spatial_report_context(sample, [])
    assert data["total"] == 6
    assert data["total_grid_cells"] == 3
    assert data["top_three_count"] == 6
    top = data["top_grids"][0]
    assert top["bbox"] == [124.0, 45.0, 124.25, 45.25]
    assert top["center"] == [124.125, 45.125]
    assert top["count"] == 3
    assert top["share_percent"] == 50.0
    assert top["active_days"] == 2
    assert top["peak_date"] == "2026-04-01"
    assert top["peak_count"] == 2
    assert data["top_grids"][1]["count"] == 2
    assert sum(x["count"] for x in data["top_grids"]) == data["total"]


def test_unknown_date_does_not_infer_active_days():
    data = build_spatial_report_context([
        {"longitude": 124.5, "latitude": 45.5},
        {"longitude": 124.7, "latitude": 45.7, "acquired_date": "not a date"},
    ], [])
    assert data["total"] == 2
    assert all(item["active_days"] == 0 and item["peak_date"] is None
               for item in data["top_grids"])



def test_map_image_has_numeric_coordinate_ticks_and_highlighted_focus_grid():
    import zlib

    points = [
        {"longitude": 124.12, "latitude": 45.12, "acquired_date": "2026-04-01"},
        {"longitude": 124.15, "latitude": 45.14, "acquired_date": "2026-04-02"},
    ]
    # Test an actual line that crosses this tightly zoomed map, instead
    # of asserting that a far-away province edge remains visible.
    report = build_spatial_report_context(points, [
        _poly("Jilin Province", 124.0, 45.0, 124.25, 45.25)
    ])
    image = report["map_png"]
    # Decode the true PNG RGB scanlines; no OCR or artificial map content.
    chunks = []
    position = 8
    while position < len(image):
        length = struct.unpack(">I", image[position:position+4])[0]
        kind = image[position+4:position+8]
        contents = image[position+8:position+8+length]
        if kind == b"IDAT":
            chunks.append(contents)
        position += 12 + length
        if kind == b"IEND":
            break
    pixels = zlib.decompress(b"".join(chunks))
    assert len(pixels) == 500 * (1 + 900 * 3)
    # Highlighted hotspot box, real FIRMS points, geographic boundary,
    # and dark tick-label pixels should all be present.
    assert bytes([215, 135, 19]) in pixels
    assert bytes([224, 75, 60]) in pixels
    assert bytes([82, 140, 164]) in pixels
    assert bytes([70, 103, 117]) in pixels
