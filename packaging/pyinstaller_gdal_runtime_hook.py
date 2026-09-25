from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys


if getattr(sys, "frozen", False):
    bundle_dir = Path(
        getattr(sys, "_MEIPASS")
    )

    gdal_data = (
        bundle_dir
        / "gdal_data"
    )

    proj_data = (
        bundle_dir
        / "proj_data"
    )

    gdal_plugins = (
        bundle_dir
        / "gdalplugins"
    )

    if gdal_data.is_dir():
        os.environ["GDAL_DATA"] = str(
            gdal_data
        )

    if proj_data.is_dir():
        # PROJ DATA EARLY INIT V2
        os.environ["PROJ_DATA"] = str(
            proj_data
        )
        os.environ["PROJ_LIB"] = str(
            proj_data
        )

    if gdal_plugins.is_dir():
        os.environ[
            "GDAL_DRIVER_PATH"
        ] = str(
            gdal_plugins
        )

    if (
        os.name == "nt"
        and hasattr(
            os,
            "add_dll_directory",
        )
    ):
        # Keep the directory handle alive for the lifetime
        # of the process so native GDAL/plugin dependencies
        # can continue to resolve.
        _gdal_dll_dir_handle = (
            os.add_dll_directory(
                str(bundle_dir)
            )
        )

# SHAPELY GEOS PRELOAD V1
# Run before application imports. On Windows, preload the exact GEOS pair
# from the PyInstaller bundle by absolute path.
_geos_preload_handles = []

if (
    getattr(sys, "frozen", False)
    and os.name == "nt"
):
    _geos_bundle_dir = Path(
        getattr(sys, "_MEIPASS")
    )

    _current_path = os.environ.get(
        "PATH",
        "",
    )

    if not _current_path.startswith(
        str(_geos_bundle_dir)
    ):
        os.environ["PATH"] = (
            str(_geos_bundle_dir)
            + os.pathsep
            + _current_path
        )

    if hasattr(
        os,
        "add_dll_directory",
    ):
        _geos_dll_dir_handle = (
            os.add_dll_directory(
                str(_geos_bundle_dir)
            )
        )

    for _geos_name in (
        "geos.dll",
        "geos_c.dll",
    ):
        _geos_path = (
            _geos_bundle_dir
            / _geos_name
        )

        if not _geos_path.is_file():
            raise RuntimeError(
                "Packaged GEOS DLL is missing: "
                + str(_geos_path)
            )

        _geos_preload_handles.append(
            ctypes.WinDLL(
                str(_geos_path)
            )
        )

