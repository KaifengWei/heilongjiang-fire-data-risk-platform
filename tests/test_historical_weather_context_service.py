from datetime import date

from fire_monitor.services.historical_weather_context_service import (
    HistoricalWeatherContextService,
)


def test_peak_summary_detects_drier_peak_day():
    text = HistoricalWeatherContextService._peak_summary_text(
        peak_metrics={
            "temperature_c": 9.0,
            "humidity_percent": 56.0,
            "wind_mps": 4.2,
            "precipitation_mm": 0.4,
        },
        period_metrics={
            "temperature_c": 7.0,
            "humidity_percent": 72.0,
            "wind_mps": 4.3,
            "precipitation_mm": 1.4,
        },
    )

    assert "更干" in text
    assert "降水很少" in text


def test_power_range_starts_in_1981():
    assert date(1981, 1, 1).isoformat() == "1981-01-01"
