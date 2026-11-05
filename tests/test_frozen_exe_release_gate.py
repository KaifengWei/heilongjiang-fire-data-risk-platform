"""Release gate checks actual EXE subprocess status and self-test JSON."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_frozen_exe import check_frozen_exe


def _fake_packaged_exe(tmp_path):
    app_dir = tmp_path / "dist" / "农业秸秆焚烧区域火点检测与分析平台"
    app_dir.mkdir(parents=True)
    (app_dir / (app_dir.name + ".exe")).write_bytes(b"synthetic fixture")
    return app_dir


def test_frozen_gate_accepts_verified_self_test_and_isolates_user_data(
    tmp_path, monkeypatch,
):
    app_dir = _fake_packaged_exe(tmp_path)
    real_user_root = str(tmp_path / "real_user_root")
    monkeypatch.setenv("LOCALAPPDATA", real_user_root)
    monkeypatch.setenv("FIRE_MONITOR_RUNTIME_DIR", "real_user_runtime")

    def run_stub(args, **kwargs):
        assert args[0] == str(app_dir / (app_dir.name + ".exe"))
        assert args[1] == "--self-test"
        assert kwargs["cwd"] == str(app_dir)
        assert kwargs["env"]["LOCALAPPDATA"] != real_user_root
        assert "FIRE_MONITOR_RUNTIME_DIR" not in kwargs["env"]
        assert kwargs["timeout"] == 120
        Path(args[2]).write_text(json.dumps({
            "ok": True, "checks": ["DOCX export"], "sample_observations": 3,
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scripts.check_frozen_exe.subprocess.run", run_stub)
    result = check_frozen_exe(app_dir)
    assert result["ok"] is True
    assert result["checks"] == ["DOCX export"]


def test_frozen_gate_refuses_failed_export_even_if_executable_returns_zero(
    tmp_path, monkeypatch,
):
    app_dir = _fake_packaged_exe(tmp_path)

    def run_stub(args, **kwargs):
        Path(args[2]).write_text(json.dumps({
            "ok": False,
            "stage": "DOCX export with spatial map",
            "error": "Required native runtime is unavailable",
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scripts.check_frozen_exe.subprocess.run", run_stub)
    with pytest.raises(RuntimeError, match="DOCX export with spatial map"):
        check_frozen_exe(app_dir)


def test_frozen_gate_refuses_missing_result_and_missing_exe(
    tmp_path, monkeypatch,
):
    app_dir = _fake_packaged_exe(tmp_path)
    monkeypatch.setattr(
        "scripts.check_frozen_exe.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    with pytest.raises(RuntimeError, match="未产生自检结果文件"):
        check_frozen_exe(app_dir)
    (app_dir / (app_dir.name + ".exe")).unlink()
    with pytest.raises(FileNotFoundError, match="EXE not found"):
        check_frozen_exe(app_dir)
