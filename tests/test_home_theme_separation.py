"""Home-only visual treatment must never leak into functional pages."""
from fire_monitor.app import create_app


def test_orbit_cover_has_no_caption_text(tmp_path):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    page = app.test_client().get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'class="app-body home-body"' in html
    assert "home-orbit-image" in html
    assert "地球遥感视觉封面" not in html
    assert "仅用于首页视觉展示" not in html
    assert "home-visual-caption" not in html
    assert "home-visual-topline" not in html


def test_start_analysis_retains_light_business_layout(tmp_path):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    html = app.test_client().get("/analyze").get_data(as_text=True)
    assert '<body class="app-body">' in html
    assert 'class="app-body home-body"' not in html
    assert "开始区域火点分析" in html
    assert "补充/保存 GeoJSON 地区边界" in html
    assert "整份 CSV" in html
