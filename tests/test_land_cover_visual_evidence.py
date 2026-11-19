"""Actual MCD12Q1 pixel previews, safe fallback and result-page pairing."""

import base64
from io import BytesIO

import numpy as np

from fire_monitor.app import create_app
from fire_monitor.services.land_cover_visual_service import build_surface_raster_previews


def _install_raster(service, monkeypatch):
    # A tiny in-memory classified raster with two distinct *real pixel*
    # categories, not an RGB photo or a decorative CSS pattern.
    image = np.full((80, 80), 3, dtype=np.uint8)  # forest
    image[6, 22] = 12  # 110.5E, 30.5N -> cropland
    image[9, 25] = 13  # 127.5E, 45.5N -> urban / other
    service._array = image
    service._inverse = (0.0, 0.2, 0.0, 0.0, 0.0, 0.2)
    service._transform = None
    service._nodata = 255
    monkeypatch.setattr(service, "_open", lambda: True)


def _representatives():
    return {
        "farmland": {
            "longitude": 110.5, "latitude": 30.5,
            "class_id": 12, "date": "2026-04-01",
        },
        "other": {
            "longitude": 127.5, "latitude": 45.5,
            "class_id": 13, "date": "2026-04-02",
        },
    }


def test_genuine_raster_pixel_neighborhoods_are_encoded_from_sampled_array(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    service = app.extensions["land_cover_context_service"]
    _install_raster(service, monkeypatch)
    previews = build_surface_raster_previews(service, _representatives())
    assert set(previews) == {"farmland", "other"}
    assert previews["farmland"]["class_id"] == 12
    assert previews["other"]["class_id"] == 13
    assert previews["farmland"]["longitude"] == 110.5
    for name, item in previews.items():
        assert item["src"].startswith("data:image/svg+xml;base64,")
        markup = base64.b64decode(item["src"].split(",", 1)[1]).decode()
        assert markup.startswith("<svg ")
        assert markup.endswith("</svg>")
        assert "role=\"img\"" in markup
        assert "http:" not in markup.replace('xmlns="http://www.w3.org/2000/svg"', "")
        assert "#3f8764" in markup  # surrounding forest pixels
        assert "<circle " in markup  # actual observation point marker
        if name == "farmland":
            assert "#c6b55d" in markup  # actual cropland pixel
        else:
            assert "#c17e75" in markup  # actual urban pixel


def test_absent_or_mismatching_raster_cannot_generate_false_preview(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    service = app.extensions["land_cover_context_service"]
    assert build_surface_raster_previews(service, _representatives()) == {}
    _install_raster(service, monkeypatch)
    invalid = _representatives()
    invalid["farmland"]["class_id"] = 14  # pixel is actually class 12
    previews = build_surface_raster_previews(service, invalid)
    assert "farmland" not in previews
    assert "other" in previews
    assert build_surface_raster_previews(service, {}) == {}


def test_actual_landcover_preview_on_result_page_and_unmodified_counts(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    service = app.extensions["land_cover_context_service"]
    _install_raster(service, monkeypatch)
    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "30.5,110.5,2026-04-01,0320,N,VIIRS,n,2.0NRT,8.5\n"
        "30.5,110.6,2026-04-01,0325,N,VIIRS,n,2.0NRT,7.1\n"
        "45.5,127.5,2026-04-02,0330,N,VIIRS,n,2.0NRT,5.0\n"
    )
    client = app.test_client()
    response = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode("utf-8")), "firms.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    page = client.get(response.headers["Location"])
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert html.count("data:image/svg+xml;base64,") == 2
    assert "实测分类栅格邻域" in html
    assert "东经 110.5000°，北纬 30.5000°" in html
    assert "东经 127.5000°，北纬 45.5000°" in html
    assert "分类像元，不是真彩色照片" in html
    assert "已匹配观测的地表类型构成" in html
    assert "耕地与混合植被背景" in html
    assert "其他地表背景" in html



def test_result_template_jinja_compiles_with_actual_sample_cards():
    """Catch malformed conditional tags before any Windows EXE build."""
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader

    templates = Path(__file__).resolve().parents[1] / "templates"
    Environment(loader=FileSystemLoader(str(templates))).get_template(
        "task_detail.html"
    )
