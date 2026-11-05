"""Validate onedir PyInstaller runtime contents, without running the GUI.

The check reads only the build output. It never touches installed GeoJSON,
uploaded CSVs, analysis history or other user data.
"""
from __future__ import annotations
import argparse
from pathlib import Path

REQUIRED_FILES = (
    "static/product.js",
    "static/map_viewport.js",
    "static/product.css",
    "templates/index.html",
    "templates/analyze.html",
    "templates/task_detail.html",
    "static/images/home_earth_orbit.webp",
    "proj_data/proj.db",
    "geos.dll",
    "geos_c.dll",
    "gdalplugins/gdal_GRIB.dll",
)


def missing_bundle_items(app_dir: str | Path) -> list[str]:
    app_dir = Path(app_dir)
    internal = app_dir / "_internal"
    if not internal.is_dir():
        return ["_internal/"]
    expected_exe = app_dir / (app_dir.name + ".exe")
    missing = []
    if not expected_exe.is_file() or expected_exe.stat().st_size == 0:
        missing.append(expected_exe.name)
    for rel in REQUIRED_FILES:
        path = internal / rel
        if not path.is_file() or path.stat().st_size == 0:
            missing.append("_internal/" + rel)
    for rel in ("gdal_data", "data/regions"):
        if not (internal / rel).is_dir():
            missing.append("_internal/" + rel + "/")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="核对 Windows EXE 完整运行资源。")
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    missing = missing_bundle_items(args.app_dir)
    if missing:
        print("打包资源缺失：")
        for item in missing:
            print("  -", item)
        return 1
    print("Windows bundle verified:", args.app_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
