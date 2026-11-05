"""Weather timeline, dynamic GFS scope and coordinate-task regressions.

Network calls are isolated with test doubles; live data availability is
checked separately during Windows acceptance.
"""

from collections import Counter
from datetime import date
from io import BytesIO

from fire_monitor.app import create_app
from fire_monitor.services.gfs_weather_context_service import GfsWeatherContextService
from fire_monitor.services.historical_weather_context_service import (
    HistoricalWeatherContextService,
)


def test_daily_weather_comparison_preserves_zero_fires_and_missing_metrics():
    series = {
        "T2M": {"20260403": 3.5, "20260404": 7.0, "20260405": 4.5},
        "RH2M": {"20260403": 72.0, "20260405": 50.0},
        "WS10M": {"20260403": 3.0, "20260404": 2.0, "20260405": 4.0},
        "PRECTOTCORR": {"20260403": 0.0, "20260404": 2.5, "20260405": 0.0},
    }
    result = HistoricalWeatherContextService._daily_comparison(
        [series],
        Counter({date(2026, 4, 3): 4, date(2026, 4, 5): 9}),
        date(2026, 4, 3),
        date(2026, 4, 5),
    )
    assert [day["fire_count"] for day in result] == [4, 0, 9]
    assert result[0]["precipitation_mm"] == 0.0
    assert result[1]["humidity_percent"] is None
    assert result[2]["temperature_c"] == 4.5


def test_power_invalid_json_is_not_cached(tmp_path, monkeypatch):
    service = HistoricalWeatherContextService(tmp_path / "power")
    class FakeResponse:
        status_code = 200
        @staticmethod
        def json():
            return {"error": "not a valid POWER parameter result"}
    monkeypatch.setattr(
        "fire_monitor.services.historical_weather_context_service.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    result = service._fetch_power(
        latitude=45.12,
        longitude=124.13,
        start=date(2026, 4, 3),
        end=date(2026, 4, 5),
    )
    assert result is None
    assert not list((tmp_path / "power" / "points").glob("*.json"))


def test_coordinate_word_weather_cache_only_never_calls_power_network(tmp_path, monkeypatch):
    service = HistoricalWeatherContextService(tmp_path / "power")
    requested = []
    monkeypatch.setattr(service, "_fetch_power", lambda **kw: requested.append(kw))
    result = service.analyze_coordinate_task(
        task_id="offline-archive",
        rows=[{
            "acquired_date": "2026-04-03",
            "longitude": 124.12,
            "latitude": 45.13,
        }],
        cached_only=True,
    )
    assert not result["available"]
    assert result["reason"] == "not_cached"
    assert not requested


def test_dynamic_gfs_bounds_follow_densest_real_location(tmp_path):
    points = [
        {"longitude": 124.13, "latitude": 45.12},
        {"longitude": 124.18, "latitude": 45.14},
        {"longitude": 124.15, "latitude": 45.13},
        {"longitude": 115.0, "latitude": 36.0},
    ]
    bounds = GfsWeatherContextService.observation_bounds(points)
    assert bounds is not None
    left, bottom, right, top = bounds
    assert left < 124.13 < right
    assert bottom < 45.12 < top
    assert not (left <= 115.0 <= right)
    params = GfsWeatherContextService._params("20261105", "12", 24, bounds)
    assert 122 < float(params["leftlon"]) < 124
    assert 125 < float(params["rightlon"]) < 127
    service = GfsWeatherContextService(tmp_path / "gfs")
    assert service._cache_path("20261105", "12", 24, bounds) != service._cache_path(
        "20261105", "12", 24, (120, 42, 136, 55)
    )


def test_gfs_cache_only_mode_never_downloads(tmp_path, monkeypatch):
    service = GfsWeatherContextService(tmp_path / "gfs")
    monkeypatch.setattr(
        service, "_candidate_cycles", lambda: [("20261105", "12")]
    )
    class NeverOnline:
        def get(self, *args, **kwargs):
            raise AssertionError("cached-only path called network")
    monkeypatch.setattr(
        "fire_monitor.services.gfs_weather_context_service.requests.Session",
        lambda: NeverOnline(),
    )
    # The service still sets headers on the session; use an actual compatible stub.
    class OfflineSession(NeverOnline):
        headers = {}
    monkeypatch.setattr(
        "fire_monitor.services.gfs_weather_context_service.requests.Session",
        lambda: OfflineSession(),
    )
    assert service._load_bundle((123, 44, 126, 47), cached_only=True) is None


def test_recent_coordinate_task_routes_to_gfs_not_historical(tmp_path, monkeypatch):
    gfs_called = []
    monkeypatch.setattr(
        GfsWeatherContextService, "task_is_recent",
        lambda self, task, rows, **kw: True,
    )
    def mock_gfs(self, *, task, rows, **kw):
        gfs_called.append(len(rows))
        return {
            "available": True, "source": "NOAA GFS 0.25°",
            "horizons": [], "overall": "test recent data",
        }
    monkeypatch.setattr(GfsWeatherContextService, "analyze", mock_gfs)
    def no_history(*args, **kwargs):
        raise AssertionError("recent coordinate task used historical route")
    monkeypatch.setattr(
        HistoricalWeatherContextService, "analyze_coordinate_task", no_history
    )
    app = create_app(
        database_path=tmp_path / "db.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    client = app.test_client()
    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "45.13,124.13,2026-11-05,0320,N,VIIRS,n,2.0NRT,4.0\n"
    )
    response = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode()), "recent.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    task_id = response.headers["Location"].rstrip("/").split("/")[-1]
    weather = client.get(f"/api/tasks/{task_id}/weather-context").get_json()
    assert weather["available"]
    assert weather["source"] == "NOAA GFS 0.25°"
    assert gfs_called == [1]


def test_weather_ui_has_daily_comparison_and_retry():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    weather_js = (root / "static" / "weather_context.js").read_text(encoding="utf-8")
    css = (root / "static" / "product.css").read_text(encoding="utf-8")
    assert "renderDailyComparison(data)" in weather_js
    assert "重新获取天气资料" in weather_js
    assert "weather-daily-comparison" in weather_js
    assert ".weather-daily-chart" in css
