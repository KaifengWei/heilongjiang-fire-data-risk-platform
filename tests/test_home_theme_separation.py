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
    assert "一份 CSV 中的有效观测统一分析" in html


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



def test_analysis_preview_copy_is_concise_and_readable(tmp_path):
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    client = app.test_client()
    result = client.get("/analyze")
    assert result.status_code == 200
    html = result.get_data(as_text=True)
    for removed in (
        "不填写矩形即分析整份 CSV",
        "分析结果中的位置与数量以实际数据为准",
        "通常不需要调整；展开后横向使用完整页面宽度",
        "不等于 NASA 下载时选择的区域",
        "不填写时保留整份 CSV 的有效观测",
        "analysis-preview-footnote",
    ):
        assert removed not in html

    assert "确认 CSV 文件及可选区域参数后开始分析" not in html
    assert "两种范围的区别" in html
    assert "当前文件中有效火点的实际坐标范围" in html
    assert "填写后，仅筛选本次分析数据" in html
    for control in (
        "autoAnalyzeForm", "analysisFiles", "declaredAreaLabel",
        "requestBbox", "observationPreviewButton", "observationPreviewInfo",
        "regionPreviewButton", "agriculturalCalendarSaveButton",
        "analyzeButton",
    ):
        assert html.count('id="' + control + '"') == 1

    css = client.get("/static/product.css").get_data(as_text=True)
    assert ".analysis-preview-guidance > strong" in css
    assert "font-size: 17px;" in css
    assert ".analysis-preview-guidance p {" in css
    assert "font-size: 14px;" in css
    assert ".analysis-preview-guidance p + p" in css

    javascript = client.get("/static/product.js").get_data(as_text=True)
    assert "这不是NASA原始下载框" not in javascript
    assert "result.valid_coordinate_rows" in javascript
