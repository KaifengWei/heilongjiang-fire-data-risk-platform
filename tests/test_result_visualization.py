"""Measured visual analysis: bar heights, denominators, and working map links."""

from datetime import date, timedelta
from io import BytesIO

from fire_monitor.app import create_app
from fire_monitor.services.report_timeline_service import prepare_web_fire_timeline


def test_daily_overview_uses_true_counts_and_zero_dates():
    start = date(2026, 4, 1)
    daily = [
        {"date": start.isoformat(), "active_fire_observation_count": 511},
        {"date": (start + timedelta(days=1)).isoformat(), "active_fire_observation_count": 408},
        {"date": (start + timedelta(days=29)).isoformat(), "active_fire_observation_count": 12},
    ]
    chart = prepare_web_fire_timeline(daily, "2026-04-01 至 2026-04-30")
    assert chart["total"] == 931
    assert chart["group_days"] == 1
    assert chart["span_days"] == 30
    assert len(chart["bars"]) == 30
    assert chart["bars"][0]["is_peak"]
    assert chart["bars"][0]["height_percent"] == 100.0
    assert chart["bars"][1]["count"] == 408
    assert 79 < chart["bars"][1]["height_percent"] < 81
    assert chart["bars"][2]["count"] == 0
    assert chart["bars"][2]["height_percent"] == 0
    assert chart["bars"][-1]["start"] == "2026-04-30"


def test_long_task_dates_are_grouped_without_inventing_observations():
    chart = prepare_web_fire_timeline(
        [
            {"date": "2026-01-01", "active_fire_observation_count": 8},
            {"date": "2026-04-30", "active_fire_observation_count": 2},
        ],
        "2026-01-01 至 2026-04-30",
    )
    assert chart["group_days"] > 1
    assert len(chart["bars"]) <= 32
    assert sum(bar["count"] for bar in chart["bars"]) == 10
    assert chart["bars"][0]["count"] == 8
    assert chart["bars"][-1]["count"] == 2
    assert prepare_web_fire_timeline([]) is None


def test_result_page_shows_interactive_real_dates_and_two_distinct_land_denominators(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "chart.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    cover = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(cover, "_open", lambda: True)
    monkeypatch.setattr(
        cover, "_sample",
        lambda longitude, latitude: 12 if longitude < 120 else None,
    )
    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "30.50,110.50,2026-04-01,0320,N,VIIRS,n,2.0NRT,8.5\n"
        "30.51,110.60,2026-04-01,0325,N,VIIRS,n,2.0NRT,9.5\n"
        "45.50,127.50,2026-04-03,0330,N,VIIRS,n,2.0NRT,7.5\n"
    )
    client = app.test_client()
    sent = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode("utf-8")), "observations.csv")},
        content_type="multipart/form-data",
    )
    assert sent.status_code == 302
    response = client.get(sent.headers["Location"])
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'class="declared-timeline-bars"' in html
    assert 'data-map-date="2026-04-01"' in html
    assert 'data-map-date="2026-04-03"' in html
    assert 'data-map-date="2026-04-02"' not in html
    assert '2026-04-02：0 条' in html
    assert "2026-04-01 · 2 条" in html

    # Coverage: 2/3 of *all* observations. Crop share: 2/2 of *matched* observations.
    assert "本次观测土地覆盖匹配比例" in html
    assert 'style="width: 66.7%"' in html
    assert "已匹配 2 条，占 66.7%；未匹配 1 条" in html
    assert "已匹配观测的地表类型构成" in html
    assert "分母为已匹配的 2 条观测，不是全部 3 条" in html
    assert 'style="width: 100.0%"' in html
    assert "耕地与混合植被背景" in html
    assert "尚未匹配土地覆盖" in html
    assert "查看统计口径与农事规则" in html


def test_all_unmatched_has_no_artificial_surface_composition(tmp_path, monkeypatch):
    app = create_app(
        database_path=tmp_path / "chart.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    cover = app.extensions["land_cover_context_service"]
    monkeypatch.setattr(cover, "_open", lambda: True)
    monkeypatch.setattr(cover, "_sample", lambda longitude, latitude: None)
    client = app.test_client()
    csv = (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "45.5,127.5,2026-04-01,0320,N,VIIRS,n,2.0NRT,8.5\n"
    )
    sent = client.post(
        "/analyze",
        data={"files": (BytesIO(csv.encode("utf-8")), "data.csv")},
        content_type="multipart/form-data",
    )
    assert sent.status_code == 302
    html = client.get(sent.headers["Location"]).get_data(as_text=True)
    assert "本次观测暂无地表匹配" in html
    assert "已匹配 0 条，占 0.0%；未匹配 1 条" in html
    assert "已匹配观测的地表类型构成" in html
    assert "暂缺可展示的具体地表类型" in html
    assert "agriculture-composition-bar" not in html
