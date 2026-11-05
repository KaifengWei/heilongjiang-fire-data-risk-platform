"""Historical NASA POWER weather for declared coordinate tasks."""

from io import BytesIO

from docx import Document

from fire_monitor.app import create_app
from fire_monitor.services.historical_weather_context_service import (
    HistoricalWeatherContextService,
)


def _mock_power(*, latitude, longitude, start, end):
    # Check coordinate sampling: the highest density quarter-degree grid.
    assert 124.0 < longitude < 124.25
    assert 45.0 < latitude < 45.25
    assert start.isoformat() == "2026-04-03"
    assert end.isoformat() == "2026-04-05"
    return {"properties": {"parameter": {
        "T2M": {"20260403": 4.0, "20260404": 8.0, "20260405": 6.0},
        "RH2M": {"20260403": 72.0, "20260404": 55.0, "20260405": 61.0},
        "WS10M": {"20260403": 2.5, "20260404": 4.1, "20260405": 3.0},
        "PRECTOTCORR": {"20260403": 1.0, "20260404": 0.0, "20260405": 0.5},
    }}}


def test_coordinate_historical_weather_uses_real_csv_location_and_export(tmp_path, monkeypatch):
    monkeypatch.setattr(HistoricalWeatherContextService, "_fetch_power", _mock_power)
    app = create_app(
        database_path=tmp_path / "data.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    client = app.test_client()
    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "45.12,124.12,2026-04-03,0320,N,VIIRS,n,2.0NRT,3.0\n"
        "45.13,124.13,2026-04-04,0320,N,VIIRS,n,2.0NRT,4.0\n"
        "45.14,124.14,2026-04-05,0320,N,VIIRS,n,2.0NRT,8.0\n"
    )
    response = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode()), "spring.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    tid = response.headers["Location"].rstrip("/").split("/")[-1]
    weather = client.get(f"/api/tasks/{tid}/weather-context").get_json()
    assert weather["available"]
    assert weather["mode"] == "historical"
    assert weather["spatial_scope"] == "representative_point"
    assert weather["source"] == "NASA POWER Daily"
    assert weather["representative_point"]["longitude"] == 124.13
    assert weather["period"]["metrics"]["temperature_c"] == 6.0
    # Source API is mocked; the service persists a real sample only when
    # _fetch_power itself writes the local cache. Test that through cache:
    # production report is intentionally cache-only.
    document = Document(BytesIO(client.get(f"/tasks/{tid}/report.docx").data))
    assert "空间位置与火点分布" in "\n".join(p.text for p in document.paragraphs)


def test_coordinate_weather_rejects_non_historical_data_without_network(tmp_path, monkeypatch):
    service = HistoricalWeatherContextService(tmp_path / "power")
    called = []
    monkeypatch.setattr(service, "_fetch_power", lambda **k: called.append(k))
    recent = [
        {"acquired_date": "2099-04-01", "longitude": 124.1, "latitude": 45.1}
    ]
    result = service.analyze_coordinate_task(task_id="future", rows=recent)
    assert result["available"] is False
    assert result["reason"] == "not_historical"
    assert called == []
