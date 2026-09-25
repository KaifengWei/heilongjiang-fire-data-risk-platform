from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def locate_bundle() -> tuple[Path, Path, Path]:
    if not DIST.is_dir():
        raise SystemExit(
            f"Missing dist directory: {DIST}"
        )

    candidates = []

    for directory in DIST.iterdir():
        if not directory.is_dir():
            continue

        internal = directory / "_internal"

        if not internal.is_dir():
            continue

        exes = list(
            directory.glob("*.exe")
        )

        if len(exes) == 1:
            candidates.append(
                (
                    directory,
                    exes[0],
                    internal,
                )
            )

    if not candidates:
        raise SystemExit(
            "No PyInstaller onedir bundle was found under dist."
        )

    candidates.sort(
        key=lambda item: item[1].stat().st_mtime,
        reverse=True,
    )

    return candidates[0]


def check_file(
    path: Path,
    label: str,
) -> bool:
    exists = path.is_file()

    if exists:
        print(
            f"[OK] {label}: "
            f"{path} "
            f"({path.stat().st_size:,} bytes)"
        )
    else:
        print(
            f"[MISSING] {label}: {path}"
        )

    return exists


def check_dir(
    path: Path,
    label: str,
) -> bool:
    exists = path.is_dir()

    if exists:
        print(
            f"[OK] {label}: {path}"
        )
    else:
        print(
            f"[MISSING] {label}: {path}"
        )

    return exists


def main() -> None:
    bundle, exe, internal = locate_bundle()

    print(
        f"Bundle: {bundle}"
    )

    print(
        f"EXE: {exe}"
    )

    print()

    checks = [
        check_file(
            internal
            / "gdalplugins"
            / "gdal_GRIB.dll",
            "GDAL GRIB plugin",
        ),
        check_dir(
            internal
            / "gdal_data",
            "GDAL data",
        ),
        check_dir(
            internal
            / "proj_data",
            "PROJ data",
        ),
        check_file(
            internal
            / "data"
            / "regions"
            / "heilongjiang_county.geojson",
            "County boundary",
        ),
        check_file(
            internal
            / "data"
            / "context"
            / "mcd12q1_2024_lc_type1.tif",
            "MCD12Q1 context raster",
        ),
        check_file(
            internal
            / "data"
            / "context"
            / "mcd12q1_2024_lc_type1.json",
            "MCD12Q1 metadata",
        ),
        check_file(
            internal
            / "data"
            / "baselines"
            / "firms_noaa20_daily.json",
            "FIRMS historical baseline",
        ),
        check_file(
            internal
            / "static"
            / "weather_context.js",
            "Weather UI",
        ),
        check_file(
            internal
            / "static"
            / "county_drilldown.js",
            "County drill-down UI",
        ),
        check_file(
            internal
            / "static"
            / "context"
            / "mcd12q1_2024_landcover.png",
            "Land-cover preview",
        ),
    ]

    print()

    if not all(checks):
        print(
            "Packaged-build verification FAILED."
        )
        raise SystemExit(1)

    print(
        "Packaged-build verification PASSED."
    )


if __name__ == "__main__":
    main()
