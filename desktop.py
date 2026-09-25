"""黑龙江省火点数据检测与风险评估平台桌面启动入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _configure_frozen_environment() -> None:
    """配置 PyInstaller 打包后的 GDAL / PROJ 数据目录。"""

    if not getattr(
        sys,
        "frozen",
        False,
    ):
        return

    bundle_root = Path(
        getattr(
            sys,
            "_MEIPASS",
            Path(sys.executable)
            .resolve()
            .parent,
        )
    )

    gdal_data = (
        bundle_root
        / "gdal_data"
    )

    proj_data = (
        bundle_root
        / "proj_data"
    )

    # FROZEN PROJ DATABASE RESOLUTION V1
    # PROJ requires the directory that directly contains proj.db.
    # Prefer the canonical packaged location, but tolerate one
    # unexpected PyInstaller nesting level if present.
    proj_database = (
        proj_data
        / "proj.db"
    )

    if not proj_database.is_file():
        candidates = list(
            proj_data.rglob("proj.db")
        ) if proj_data.is_dir() else []

        if len(candidates) == 1:
            proj_data = candidates[0].parent
            proj_database = candidates[0]

    if not proj_database.is_file():
        bundle_candidates = list(
            bundle_root.rglob("proj.db")
        )

        if len(bundle_candidates) == 1:
            proj_data = (
                bundle_candidates[0]
                .parent
            )
            proj_database = (
                bundle_candidates[0]
            )

    if gdal_data.is_dir():
        os.environ[
            "GDAL_DATA"
        ] = str(
            gdal_data
        )

    if proj_data.is_dir():

        os.environ[
            "PROJ_LIB"
        ] = str(
            proj_data
        )

        os.environ[
            "PROJ_DATA"
        ] = str(
            proj_data
        )


_configure_frozen_environment()


# FORCE FROZEN PROJ SEARCH PATH V2
def _force_frozen_proj_search_path() -> None:
    if not getattr(sys, "frozen", False):
        return

    bundle_root = Path(
        getattr(
            sys,
            "_MEIPASS",
            Path(sys.executable).resolve().parent,
        )
    )

    preferred = bundle_root / "proj_data" / "proj.db"

    if preferred.is_file():
        proj_dir = preferred.parent
    else:
        candidates = list(bundle_root.rglob("proj.db"))

        if len(candidates) != 1:
            raise RuntimeError(
                "Frozen PROJ database resolution failed: "
                f"found {len(candidates)} proj.db files under {bundle_root}"
            )

        proj_dir = candidates[0].parent

    os.environ["PROJ_DATA"] = str(proj_dir)
    os.environ["PROJ_LIB"] = str(proj_dir)

    from osgeo import gdal, osr  # noqa: E402

    gdal.SetConfigOption("PROJ_DATA", str(proj_dir))
    gdal.SetConfigOption("PROJ_LIB", str(proj_dir))

    setter = getattr(osr, "SetPROJSearchPaths", None)

    if setter is None:
        raise RuntimeError(
            "Current GDAL/OSR build does not expose SetPROJSearchPaths."
        )

    setter([str(proj_dir)])

    probe = osr.SpatialReference()
    error_code = probe.ImportFromEPSG(4326)

    if error_code != 0:
        raise RuntimeError(
            "PROJ startup self-check failed: "
            f"ImportFromEPSG(4326) returned {error_code}; "
            f"PROJ directory={proj_dir}"
        )


_force_frozen_proj_search_path()


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
)

SRC_DIR = (
    PROJECT_ROOT
    / "src"
)


if (
    not getattr(
        sys,
        "frozen",
        False,
    )
    and str(SRC_DIR)
    not in sys.path
):
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from fire_monitor.desktop import run_desktop  # noqa: E402


def main() -> None:
    """启动桌面应用。"""

    run_desktop()


if __name__ == "__main__":
    main()