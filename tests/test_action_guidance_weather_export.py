"""Regressions for wide advice cards and report/weather consistency."""

from pathlib import Path

from docx import Document

from fire_monitor.services.report_docx_service import _historical_weather_daily_table


ROOT = Path(__file__).resolve().parents[1]


def test_land_cover_text_without_image_uses_full_width():
    template = (ROOT / "templates" / "task_detail.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "product.css").read_text(encoding="utf-8")
    assert 'class="action-land-context is-text-only"' in template
    assert "is-text-only{% endif %}" in template
    assert ".action-land-context.is-text-only" in css
    assert "grid-template-columns: minmax(0,1fr)" in css
    assert ".action-guidance-facts" in css
    assert "本次火点观测摘要" in template
    assert "火点高值日" in template
    assert "有观测的日期" in template
    assert "repeat(auto-fit,minmax(min(100%,295px),1fr))" in css


def test_historical_weather_daily_table_uses_real_dates_and_null_markers():
    weather = {
        "available": True,
        "mode": "historical",
        "spatial_scope": "representative_point",
        "daily_comparison": [
            {
                "date": "2026-04-02", "fire_count": 7,
                "temperature_c": 5.0, "humidity_percent": None,
                "wind_mps": 3.3, "precipitation_mm": 0.0,
            },
            {
                "date": "2026-04-01", "fire_count": 12,
                "temperature_c": 2.5, "humidity_percent": 72.0,
                "wind_mps": 2.0, "precipitation_mm": 1.5,
            },
        ],
    }
    doc = Document()
    _historical_weather_daily_table(doc, weather)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "火点日期与天气变化对照" in text
    assert "实际代表点" in text
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert len(table.rows) == 3
    assert [cell.text for cell in table.rows[0].cells] == [
        "日期", "火点观测", "气温 (℃)",
        "湿度 (%)", "风速 (m/s)", "日降水 (mm)",
    ]
    assert table.cell(1, 0).text == "2026-04-01"
    assert table.cell(1, 1).text == "12"
    assert table.cell(2, 0).text == "2026-04-02"
    assert table.cell(2, 3).text == "—"
    assert table.cell(2, 5).text == "0.0"
    assert table.rows[0]._tr.trPr.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblHeader"
    ) is not None


def test_weather_export_skips_unavailable_data_and_limits_long_span():
    doc = Document()
    _historical_weather_daily_table(doc, {"available": False, "mode": "historical"})
    assert not doc.tables
    rows = [
        {
            "date": f"2026-04-{day:02d}" if day <= 30 else f"2026-05-{day - 30:02d}",
            "fire_count": day,
            "temperature_c": 8.0,
            "humidity_percent": 60.0,
            "wind_mps": 3.0,
            "precipitation_mm": 0.0,
        }
        for day in range(1, 61)
    ]
    _historical_weather_daily_table(doc, {
        "available": True, "mode": "historical",
        "daily_comparison": rows,
    })
    assert len(doc.tables) == 1
    assert len(doc.tables[0].rows) == 31
    assert "火点观测较多的30个日期" in "\n".join(p.text for p in doc.paragraphs)
