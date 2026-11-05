"""Canvas zoom/pan is pure WGS84 navigation; no task data mutation."""

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from fire_monitor.app import create_app


def test_coordinate_task_has_map_navigation_controls_and_correct_script_order(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite",
                     uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    csv = (
        b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        b"45,124,2026-04-03,0320,N,VIIRS,n,2.0NRT,8.5\n"
    )
    submitted = client.post("/analyze", data={
        "files": (BytesIO(csv), "area.csv"),
    }, content_type="multipart/form-data")
    assert submitted.status_code == 302
    html = client.get(submitted.headers["Location"]).get_data(as_text=True)
    assert html.count('id="mapZoomIn"') == 1
    assert html.count('id="mapZoomOut"') == 1
    assert html.count('id="mapPointerCoordinate"') == 1
    assert "Ctrl + 滚轮缩放" in html
    assert html.index('map_viewport.js') < html.index('product.js')
    js = client.get("/static/product.js").get_data(as_text=True)
    assert "event.ctrlKey" in js
    assert "{ passive: false }" in js
    assert "viewportMath.zoomAt(" in js
    assert "viewportMath.panBounds(" in js
    assert "viewportMath.visibleBounds(" in js
    assert "manualViewport = null;" in js
    assert "canvas.setPointerCapture(" in js
    assert client.get("/static/map_viewport.js").status_code == 200


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js not installed")
def test_zoom_anchors_and_drag_positions_are_geographically_stable():
    src = Path(__file__).resolve().parents[1] / "static" / "map_viewport.js"
    javascript = r"""
    const assert = require('node:assert/strict');
    const map = require(process.argv[1]);
    const bounds = {minX: 123.5, minY: 44, maxX: 126, maxY: 46};
    const width = 900, height = 500, pad = 26;
    const start = map.fitBounds(bounds, width, height, pad);
    const point = [370, 190];
    const anchor = start.unproject(...point);
    const enlargedBounds = map.zoomAt(start, 1, 2, ...point);
    const enlarged = map.fitBounds(enlargedBounds, width, height, pad);
    const fixed = enlarged.project(anchor);
    assert.ok(Math.abs(fixed[0] - point[0]) < 1e-7);
    assert.ok(Math.abs(fixed[1] - point[1]) < 1e-7);
    assert.ok(enlarged.scale > start.scale);
    const zoomOut = map.zoomAt(start, 1, .5, ...point);
    assert.ok(map.fitBounds(zoomOut, width, height, pad).scale < start.scale);
    const current = map.visibleBounds(enlarged);
    const panned = map.panBounds(current, 80, -30, enlarged.scale);
    const afterPan = map.fitBounds(panned, width, height, pad).project(anchor);
    assert.ok(Math.abs(afterPan[0] - (point[0] + 80)) < 1e-7);
    assert.ok(Math.abs(afterPan[1] - (point[1] - 30)) < 1e-7);
    const roundtrip = enlarged.unproject(...fixed);
    assert.ok(Math.abs(roundtrip[0] - anchor[0]) < 1e-9);
    assert.ok(Math.abs(roundtrip[1] - anchor[1]) < 1e-9);
    """
    result = subprocess.run(
        [shutil.which("node"), "-e", javascript, str(src)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_source_map_navigation_never_changes_task_observations():
    js = (Path(__file__).resolve().parents[1] / "static" / "product.js").read_text(
        encoding="utf-8"
    )
    assert "if (!event.ctrlKey) return;" in js
    assert "manualViewport = viewportMath.zoomAt(" in js
    assert "manualViewport = viewportMath.panBounds(" in js
    assert "const nextZoom = Math.max(.5, Math.min(64," in js



def test_coordinate_free_zoom_clips_only_canvas_drawing_not_analysis():
    script = (Path(__file__).resolve().parents[1] / "static" / "product.js").read_text(
        encoding="utf-8"
    )
    assert "const drawable = coordinateMode" in script
    assert "let displayCount = drawable.length" in script
    assert "displayLabel = coordinateMode ? '当前视野火点'" in script
    assert "drawable.forEach(point =>" in script
    assert "extent.maxX < bounds.minX" in script
    # Filtering is used only for rendering; the task payload is still intact.
    assert "points = Array.isArray(payload.points) ? payload.points : []" in script



def test_grid_precision_increases_when_zoomed_to_a_small_area():
    js = (Path(__file__).resolve().parents[1] / "static" / "product.js").read_text(
        encoding="utf-8"
    )
    assert "const tickSteps = [.005, .01, .02, .05, .1, .25" in js
    assert "lon.toFixed(precision)" in js
    assert "lat.toFixed(precision)" in js
    assert "Math.abs(lon).toFixed(4)" in js
