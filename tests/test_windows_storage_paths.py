"""User data stays available after a Windows onedir EXE is rebuilt."""

import json

from fire_monitor.services.reference_basemap_service import ReferenceBasemapStore
from fire_monitor.user_data_paths import user_data_root, desktop_runtime_dir


def test_offline_map_and_task_storage_share_existing_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    root = tmp_path / "Local" / "HeilongjiangFireMonitor"
    assert user_data_root() == root
    assert desktop_runtime_dir() == root / "runtime"
    assert ReferenceBasemapStore(desktop_runtime_dir()).path == (
        root / "runtime" / "map_background" / "reference_basemap.json"
    )


def test_desktop_flask_host_reads_existing_map_after_restart(tmp_path, monkeypatch):
    from fire_monitor.desktop import DesktopServer

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("FIRE_MONITOR_RUNTIME_DIR", str(tmp_path / "Local" / "HeilongjiangFireMonitor" / "runtime"))
    first = DesktopServer()
    store = ReferenceBasemapStore(desktop_runtime_dir())
    payload = {
        "type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {"shapeName": "Liaoning"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [121, 41], [122, 41], [122, 42], [121, 42], [121, 41],
            ]]},
        }],
    }
    store.install(json.dumps(payload).encode(), source="geoBoundaries test", authorized=True)
    original = first.app.test_client().get("/api/map/background").get_json()
    assert original["installed"]
    assert original["feature_count"] == 1
    assert (desktop_runtime_dir() / "fire_monitor.sqlite").is_file()

    second = DesktopServer()
    restored = second.app.test_client().get("/api/map/background").get_json()
    assert restored["sha256"] == original["sha256"]
    assert (desktop_runtime_dir() / "fire_monitor.sqlite").is_file()
