"""Local, observation-grounded MCD12Q1 raster previews for result cards.

These are genuine classified land-cover pixels around an actual FIRMS sample,
NOT true-colour satellite images, photos, or new land-parcel boundaries.
If an installed raster cannot verify the sample, no preview is manufactured.
"""
from __future__ import annotations

import base64
from math import isfinite
from typing import Any

from fire_monitor.services.land_cover_context_service import IGBP_GROUPS, LandCoverContextService

COLORS = {
    "agriculture": "#c6b55d",
    "forest": "#3f8764",
    "grass_shrub": "#9ab476",
    "wetland_water": "#6fafd0",
    "urban": "#c17e75",
    "barren_snow": "#d6d2c7",
}
MISSING_COLOR = "#e5ebef"
CELL_PX = 13
GRID_COLUMNS = 19
GRID_ROWS = 13


def _safe_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _raster_cell(
    service: LandCoverContextService, longitude: float, latitude: float,
) -> tuple[int, int] | None:
    inverse = getattr(service, "_inverse", None)
    if not isinstance(inverse, tuple) or len(inverse) != 6:
        return None
    x, y = longitude, latitude
    transformer = getattr(service, "_transform", None)
    if transformer is not None:
        try:
            x, y, _ = transformer.TransformPoint(x, y)
        except (TypeError, ValueError, RuntimeError):
            return None
    values = [float(v) for v in inverse]
    pixel = int(values[0] + values[1] * x + values[2] * y)
    line = int(values[3] + values[4] * x + values[5] * y)
    return pixel, line


def build_surface_raster_previews(
    service: LandCoverContextService,
    representatives: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Render up to two small static raster neighbourhoods from installed data.

    It is important that the image and its coordinate share *the same source*.
    A mocked/absent raster intentionally returns no image, even if a category
    count was computed elsewhere.
    """
    if not representatives:
        return {}
    raster = getattr(service, "_array", None)
    if raster is None or getattr(raster, "ndim", None) != 2:
        return {}
    inverse = getattr(service, "_inverse", None)
    if inverse is None:
        return {}
    nodata = getattr(service, "_nodata", None)
    height, width = raster.shape
    results: dict[str, dict[str, Any]] = {}
    for group in ("farmland", "other"):
        point = representatives.get(group) or {}
        lon = _safe_number(point.get("longitude"))
        lat = _safe_number(point.get("latitude"))
        expected = point.get("class_id")
        if lon is None or lat is None:
            continue
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        try:
            expected_id = int(expected)
            coord = _raster_cell(service, lon, lat)
        except (TypeError, ValueError, OverflowError):
            continue
        if not coord:
            continue
        px, py = coord
        if not (0 <= px < width and 0 <= py < height):
            continue
        actual = int(raster[py, px])
        if actual != expected_id or actual not in IGBP_GROUPS:
            continue
        if (group == "farmland") != (actual in (12, 14)):
            continue

        width_svg = GRID_COLUMNS * CELL_PX
        height_svg = GRID_ROWS * CELL_PX
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width_svg} {height_svg}" '
            'shape-rendering="crispEdges" role="img">',
            f'<rect width="{width_svg}" height="{height_svg}" fill="{MISSING_COLOR}"/>',
        ]
        for y in range(GRID_ROWS):
            source_y = py + y - GRID_ROWS // 2
            for x in range(GRID_COLUMNS):
                source_x = px + x - GRID_COLUMNS // 2
                if not (0 <= source_x < width and 0 <= source_y < height):
                    continue
                cls = int(raster[source_y, source_x])
                if nodata is not None and cls == int(nodata):
                    continue
                category = IGBP_GROUPS.get(cls)
                if category is None:
                    continue
                color = COLORS[category]
                parts.append(
                    f'<rect x="{x * CELL_PX}" y="{y * CELL_PX}" '
                    f'width="{CELL_PX}" height="{CELL_PX}" fill="{color}"/>'
                )
        cx = (GRID_COLUMNS // 2 + .5) * CELL_PX
        cy = (GRID_ROWS // 2 + .5) * CELL_PX
        parts += [
            f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="#ffffff" stroke-width="3"/>',
            f'<circle cx="{cx}" cy="{cy}" r="5.5" fill="none" stroke="#193b4f" stroke-width="2"/>',
            f'<path d="M {cx - 13} {cy} H {cx - 9} M {cx + 9} {cy} H {cx + 13} '
            f'M {cx} {cy - 13} V {cy - 9} M {cx} {cy + 9} V {cy + 13}" '
            'fill="none" stroke="#ffffff" stroke-width="2"/>',
            '</svg>',
        ]
        source = "".join(parts).encode("utf-8")
        results[group] = {
            "src": "data:image/svg+xml;base64," + base64.b64encode(source).decode("ascii"),
            "longitude": round(lon, 5),
            "latitude": round(lat, 5),
            "class_id": expected_id,
            "date": str(point.get("date") or ""),
            "source": "MCD12Q1 2024 LC_Type1",
            "image_type": "土地覆盖分类栅格（非真彩色影像）",
        }
    return results
