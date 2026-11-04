"""The established per-user data locations used by the Windows EXE.

Do not rename the legacy folder: existing observations, uploaded CSVs,
WebView state and installed reference maps already live there.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_DATA_FOLDER = "HeilongjiangFireMonitor"


def user_data_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    root = (Path(local_appdata) / APP_DATA_FOLDER) if local_appdata else (
        Path.home() / ".heilongjiang_fire_monitor"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def desktop_runtime_dir() -> Path:
    return user_data_root() / "runtime"
