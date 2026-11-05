"""Post-build execution check: run the *packaged* Windows EXE headlessly.

Unlike static PyInstaller bundle inspection, this verifies the bundled imports,
native CRS libraries and task-to-Word workflow. The EXE's own self-test
creates and removes its synthetic user data; no real user records are opened.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def check_frozen_exe(app_dir: Path, *, timeout: int = 120) -> dict:
    executable = app_dir / (app_dir.name + ".exe")
    if not executable.is_file():
        raise FileNotFoundError(f"Windows EXE not found: {executable}")
    with tempfile.TemporaryDirectory(prefix="fire-bundle-check-") as folder:
        temporary = Path(folder)
        report_path = temporary / "self_test_result.json"
        environment = dict(os.environ)
        environment["LOCALAPPDATA"] = str(temporary / "local_appdata")
        # This release gate must not use any caller's persisted app context.
        environment.pop("FIRE_MONITOR_RUNTIME_DIR", None)
        process = subprocess.run(
            [str(executable), "--self-test", str(report_path)],
            cwd=str(app_dir),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if not report_path.is_file():
            raise RuntimeError(
                "打包后的 EXE 未产生自检结果文件（退出码 "
                + str(process.returncode)
                + "）。请检查 PyInstaller 运行依赖。"
            )
        result = json.loads(report_path.read_text(encoding="utf-8"))
        if process.returncode != 0 or not result.get("ok"):
            raise RuntimeError(
                "EXE 自检未通过："
                + str(result.get("stage") or "startup")
                + "；"
                + str(result.get("error") or f"exit={process.returncode}")
            )
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行 Windows 打包 EXE 核心自检。")
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = check_frozen_exe(args.app_dir)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("Windows EXE 核心自检失败：", exc)
        return 1
    print("Windows EXE core self-test verified:")
    for check in result["checks"]:
        print("  OK", check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
