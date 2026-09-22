from datetime import date

from fire_monitor.services.gfs_weather_context_service import (
    GfsWeatherContextService,
)


def test_weather_context_excludes_historical_task(tmp_path):
    service = GfsWeatherContextService(tmp_path / "weather")

    assert service.task_is_recent(
        {"analysis_end": "2025-04-30"},
        [{"acquired_date": "2025-04-30"}],
        today=date(2026, 9, 21),
    ) is False


def test_weather_context_accepts_recent_task(tmp_path):
    service = GfsWeatherContextService(tmp_path / "weather")

    assert service.task_is_recent(
        {"analysis_end": "2026-09-20"},
        [],
        today=date(2026, 9, 21),
    ) is True


def test_weather_judgement_marks_dry_and_windy_as_attention():
    result = GfsWeatherContextService.evaluate_conditions(
        temperature=24.0,
        humidity=31.0,
        wind_speed=7.2,
        precipitation=0.0,
    )

    assert result["state"] == "建议提高关注"
    assert result["tone"] == "alert"


def test_weather_judgement_marks_rain_as_easing():
    result = GfsWeatherContextService.evaluate_conditions(
        temperature=18.0,
        humidity=70.0,
        wind_speed=3.0,
        precipitation=12.0,
    )

    assert result["state"] == "条件明显趋缓"
    assert result["tone"] == "easing"

def test_weather_context_assets_are_mounted_in_task_template():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "templates"
        / "task_detail.html"
    ).read_text(encoding="utf-8")

    assert 'id="weatherContextPanel"' in template
    assert "weather_context.js" in template

def test_localized_watch_elevates_horizon_guidance():
    province = {
        "state": "条件相对平稳",
        "tone": "normal",
        "summary": "未来气象条件整体较平稳。",
    }

    counties = [
        {
            "county_name": "双城区",
            "tone": "watch",
        },
        {
            "county_name": "桦川县",
            "tone": "normal",
        },
    ]

    result = GfsWeatherContextService.combine_horizon_guidance(
        province,
        counties,
    )

    assert result["tone"] == "watch"
    assert result["state"] == "局部建议继续关注"
    assert "双城区" in result["summary"]


def test_localized_alert_elevates_horizon_guidance():
    province = {
        "state": "条件相对平稳",
        "tone": "normal",
        "summary": "未来气象条件整体较平稳。",
    }

    counties = [
        {
            "county_name": "五常市",
            "tone": "alert",
        },
        {
            "county_name": "双城区",
            "tone": "watch",
        },
    ]

    result = GfsWeatherContextService.combine_horizon_guidance(
        province,
        counties,
    )

    assert result["tone"] == "alert"
    assert result["state"] == "局部需提高关注"
    assert "五常市" in result["summary"]

def test_weather_ui_contains_plain_language_guidance_and_motion():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    weather_js = (
        root
        / "static"
        / "weather_context.js"
    ).read_text(encoding="utf-8")

    css = (
        root
        / "static"
        / "product.css"
    ).read_text(encoding="utf-8")

    assert "建议怎么做" in weather_js
    assert "空气偏干" in weather_js
    assert "weather-motion" in weather_js
    assert "VISUAL SYSTEM V2" in css

def test_historical_weather_ui_uses_historical_mode():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    weather_js = (
        root
        / "static"
        / "weather_context.js"
    ).read_text(encoding="utf-8")

    assert "data.mode === 'historical'" in weather_js
    assert "任务期间天气背景" in weather_js
    assert "NASA POWER Daily" in weather_js


def test_weather_motion_uses_smooth_effects():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    css = (
        root
        / "static"
        / "product.css"
    ).read_text(encoding="utf-8")

    assert "WEATHER VISIBILITY + NATURAL MOTION V2.1" in css
    assert "weather-breeze" in css
    assert "weather-drop" in css
    assert "prefers-reduced-motion" in css

def test_weather_ui_has_loading_stage_and_natural_reveal():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    weather_js = (
        root
        / "static"
        / "weather_context.js"
    ).read_text(encoding="utf-8")
    css = (
        root
        / "static"
        / "product.css"
    ).read_text(encoding="utf-8")

    assert "正在生成天气背景与建议" in weather_js
    assert "weather-loading-track" in weather_js
    assert "weather-panel-reveal" in css
    assert "weather-loading-progress" in css


def test_historical_weather_ui_uses_compact_non_defensive_copy():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    weather_js = (
        root
        / "static"
        / "weather_context.js"
    ).read_text(encoding="utf-8")

    assert "结合任务日期和重点县区，查看火点出现时的天气条件。" in weather_js
    assert "任务期平均天气" in weather_js
    assert "不代表预报，也不能单独证明火点成因" not in weather_js
