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