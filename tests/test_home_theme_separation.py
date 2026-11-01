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


def test_analysis_workbench_keeps_single_form_and_all_existing_controls(tmp_path):
    """New 60/40 layout must preserve the working upload workflow."""
    from html.parser import HTMLParser

    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    page = app.test_client().get("/analyze")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "本软件面向农业相关区域的 FIRMS 火点观测分析。" in html
    assert "analysis-intro-band" in html
    assert "analysis-workbench-layout" in html
    assert "analysis-workbench-inputs" in html
    assert "analysis-workbench-preview" in html
    assert "analysis-workbench-extras" in html

    class FormControls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.ids = []
            self.details = []
            self.forms = 0

        def handle_starttag(self, tag, attrs):
            props = dict(attrs)
            if tag == "form":
                self.forms += 1
                if props.get("id") == "autoAnalyzeForm":
                    self.depth += 1
            if self.depth:
                if props.get("id"):
                    self.ids.append(props["id"])
                if tag == "details":
                    self.details.append(props.get("class", ""))

        def handle_endtag(self, tag):
            if tag == "form" and self.depth:
                self.depth -= 1

    controls = FormControls()
    controls.feed(html)
    assert controls.forms == 1
    for control_id in (
        "analysisFiles", "declaredAreaLabel", "requestBbox",
        "observationPreviewButton", "observationPreviewInfo",
        "regionPreviewButton", "regionCatalogSaveButton",
        "agriculturalCalendarSaveButton", "analyzeButton", "analysisProgress",
    ):
        assert controls.ids.count(control_id) == 1, control_id

    assert "advanced-boundary-workflow" in controls.details
    assert "agricultural-calendar-advanced" in controls.details
    assert "name=\"use_boundary_scope\"" in html
    assert "enctype=\"multipart/form-data\"" in html
    assert "<body class=\"app-body\">" in html

    stylesheet = app.test_client().get("/static/product.css")
    assert stylesheet.status_code == 200
    assert ".analyze-page-main .analysis-workbench-layout" in stylesheet.get_data(as_text=True)
