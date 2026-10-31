"""The Earth cover theme is exclusive to home; all app routes stay light."""
from fire_monitor.app import create_app


def test_home_cover_has_no_overlaid_labels_and_business_pages_use_light_theme(tmp_path):
    app = create_app(database_path=tmp_path / "db.sqlite",
                     uploads_root=tmp_path / "uploads", testing=True)
    client = app.test_client()
    home = client.get("/").get_data(as_text=True)
    assert 'class="app-body home-body"' in home
    assert "home-orbit-image" in home
    assert "home_earth_orbit.webp" in home
    assert "home-visual-topline" not in home
    assert "home-visual-caption" not in home
    assert "地球遥感视觉封面" not in home
    assert "区域火点检测与分析平台" in home

    for path in ("/analyze", "/tasks"):
        page = client.get(path).get_data(as_text=True)
        assert 'class="app-body"' in page
        assert 'class="app-body home-body"' not in page
    assert "高级功能：精确行政区分析与 GeoJSON 边界（选用）" in client.get("/analyze").get_data(as_text=True)
