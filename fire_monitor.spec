# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
)

try:
    from PyInstaller.utils.hooks import (
        conda as conda_support,
    )
except ImportError:
    conda_support = None


PROJECT_ROOT = (
    Path.cwd()
    .resolve()
)

SRC_DIR = (
    PROJECT_ROOT
    / "src"
)

APP_NAME = (
    "黑龙江省火点数据检测与风险评估平台"
)


datas = [
    (
        str(
            PROJECT_ROOT
            / "templates"
        ),
        "templates",
    ),
    (
        str(
            PROJECT_ROOT
            / "static"
        ),
        "static",
    ),
    (
        str(
            PROJECT_ROOT
            / "data"
            / "regions"
        ),
        "data/regions",
    ),
]



# PACKAGED PRODUCT CONTEXT DATA V1
datas += [
    (
        str(
            PROJECT_ROOT
            / "data"
            / "baselines"
        ),
        "data/baselines",
    ),
    (
        str(
            PROJECT_ROOT
            / "data"
            / "context"
        ),
        "data/context",
    ),
]

binaries = []
hiddenimports = []


# ---------------------------------------------------------
# GDAL Python 包
# ---------------------------------------------------------

(
    osgeo_datas,
    osgeo_binaries,
    osgeo_hiddenimports,
) = collect_all(
    "osgeo"
)

datas += (
    osgeo_datas
)

binaries += (
    osgeo_binaries
)

hiddenimports += (
    osgeo_hiddenimports
)


# ---------------------------------------------------------
# Conda 环境中的 GDAL / PROJ 动态库
# ---------------------------------------------------------

if (
    conda_support
    is not None
):

    try:

        binaries += (
            conda_support
            .collect_dynamic_libs(
                "gdal",
                dest=".",
                dependencies=True,
            )
        )

    except Exception as exc:

        print(
            "[build warning] "
            "Conda GDAL DLL 自动收集失败：",
            exc,
        )


# ---------------------------------------------------------
# GDAL / PROJ 数据目录
# ---------------------------------------------------------

conda_prefix = (
    os.environ.get(
        "CONDA_PREFIX"
    )
)

if conda_prefix:

    conda_prefix = (
        Path(conda_prefix)
    )

    gdal_share = (
        conda_prefix
        / "Library"
        / "share"
        / "gdal"
    )

    proj_share = (
        conda_prefix
        / "Library"
        / "share"
        / "proj"
    )

    if gdal_share.is_dir():

        datas.append(
            (
                str(
                    gdal_share
                ),
                "gdal_data",
            )
        )

    if proj_share.is_dir():

        datas.append(
            (
                str(
                    proj_share
                ),
                "proj_data",
            )
        )


    # PROJ DATABASE DIRECT PACKAGING V1
    # Keep the whole PROJ data directory, but also force proj.db
    # into the exact runtime location expected by the frozen app.
    proj_database = (
        proj_share
        / "proj.db"
    )

    if not proj_database.is_file():
        raise RuntimeError(
            "Required PROJ database is missing: "
            + str(proj_database)
        )

    datas.append(
        (
            str(proj_database),
            "proj_data",
        )
    )


    # SHAPELY GEOS RUNTIME V1
    # Shapely installed from Conda links against GEOS under Library/bin.
    # Bundle these exact binaries explicitly.
    for geos_name in (
        "geos.dll",
        "geos_c.dll",
    ):
        geos_binary = (
            conda_prefix
            / "Library"
            / "bin"
            / geos_name
        )

        if not geos_binary.is_file():
            raise RuntimeError(
                "Required Shapely/GEOS DLL is missing: "
                + str(geos_binary)
            )

        binaries.append(
            (
                str(geos_binary),
                ".",
            )
        )


    # GDAL GRIB PLUGIN V1
    grib_plugin = (
        conda_prefix
        / "Library"
        / "lib"
        / "gdalplugins"
        / "gdal_GRIB.dll"
    )

    if not grib_plugin.is_file():
        raise RuntimeError(
            "Required GDAL GRIB plugin is missing: "
            + str(grib_plugin)
        )

    binaries.append(
        (
            str(grib_plugin),
            "gdalplugins",
        )
    )


a = Analysis(
    [
        str(
            PROJECT_ROOT
            / "desktop.py"
        ),
    ],
    pathex=[
        str(
            SRC_DIR
        ),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(
            PROJECT_ROOT
            / "packaging"
            / "pyinstaller_gdal_runtime_hook.py"
        ),
    ],
    excludes=[],
    noarchive=False,
)


pyz = PYZ(
    a.pure,
)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)


coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)