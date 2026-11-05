"""The no-GUI desktop self-test uses only a throwaway user-data root."""

import json

from fire_monitor.desktop_self_test import run_self_test


def test_desktop_release_self_test_round_trip_and_does_not_touch_user_data(
    tmp_path, monkeypatch,
):
    permanent = tmp_path / "real_localappdata"
    permanent.mkdir()
    sentinel = permanent / "do_not_modify.txt"
    sentinel.write_text("original user data", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(permanent))
    monkeypatch.setenv("FIRE_MONITOR_RUNTIME_DIR", str(tmp_path / "existing_runtime"))

    report = tmp_path / "out" / "release.json"
    assert run_self_test(report) == 0
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["sample_observations"] == 3
    assert "DOCX report, real point, GeoJSON join and embedded map" in result["checks"]
    assert sentinel.read_text(encoding="utf-8") == "original user data"
    assert list(permanent.iterdir()) == [sentinel]
    assert (tmp_path / "existing_runtime").exists() is False
    assert __import__("os").environ["LOCALAPPDATA"] == str(permanent)
    assert __import__("os").environ["FIRE_MONITOR_RUNTIME_DIR"] == str(
        tmp_path / "existing_runtime"
    )
