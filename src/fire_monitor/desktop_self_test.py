"""Run an isolated end-to-end core check inside the installed Windows EXE.

No GUI, server listener, real user's database, CSV files or maps are touched.
For Windows release validation this module executes *inside* the PyInstaller
process, so missing imports or native spatial DLLs fail the build gate.
"""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile

from docx import Document


def run_self_test(report_path: Path) -> int:
    checks: list[str] = []
    original_env = {
        name: os.environ.get(name)
        for name in ("LOCALAPPDATA", "FIRE_MONITOR_RUNTIME_DIR")
    }
    outcome: dict = {"ok": False, "checks": checks}
    stage = "initialization"
    try:
        with tempfile.TemporaryDirectory(prefix="firms-exe-selftest-") as sandbox:
            # Override both persistent roots BEFORE creating the desktop host.
            os.environ["LOCALAPPDATA"] = str(Path(sandbox) / "user_data")
            os.environ["FIRE_MONITOR_RUNTIME_DIR"] = str(
                Path(sandbox) / "user_data" / "HeilongjiangFireMonitor" / "runtime"
            )
            from fire_monitor.desktop import DesktopServer
            # Linux CI tests the Python/Flask core without a window manager.
            # Only frozen release self-tests need the actual GUI import.
            if getattr(__import__("sys"), "frozen", False):
                import webview  # noqa: F401
            from osgeo import osr
            from shapely.geometry import Point

            sr = osr.SpatialReference()
            assert sr.ImportFromEPSG(4326) == 0
            assert Point(124.0, 45.0).is_valid
            checks.append("native spatial libraries and pywebview")

            host = DesktopServer()
            client = host.app.test_client()
            stage = "templates and static assets"
            for uri in ("/", "/analyze", "/static/product.js",
                        "/static/map_viewport.js", "/static/product.css"):
                response = client.get(uri)
                assert response.status_code == 200, (
                    f"{uri}: HTTP {response.status_code}"
                )
            checks.append("homepage, analysis page and map assets")

            stage = "offline GeoJSON installation"
            basemap = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"shapeName": "Jilin Province"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [123, 44], [126, 44], [126, 46],
                            [123, 46], [123, 44],
                        ]],
                    },
                }],
            }
            installed = client.post(
                "/api/map/background",
                data={
                    "background_file": (
                        BytesIO(json.dumps(basemap).encode("utf-8")),
                        "self_test.geojson",
                    ),
                    "source": "EXE isolated release self-test",
                    "authorized": "yes",
                },
                content_type="multipart/form-data",
            )
            assert installed.status_code == 200, (
                f"GeoJSON upload HTTP {installed.status_code}"
            )
            checks.append("offline GeoJSON installation")

            stage = "FIRMS CSV upload and record"
            csv = (
                "latitude,longitude,acq_date,acq_time,satellite,instrument,"
                "confidence,version,frp\n"
                "45.12,124.12,2026-04-03,0320,N,VIIRS,n,2.0NRT,8.5\n"
                "45.16,124.16,2026-04-04,0320,N,VIIRS,n,2.0NRT,6.0\n"
                "45.14,125.35,2026-04-04,0320,N,VIIRS,n,2.0NRT,5.1\n"
            )
            uploaded = client.post(
                "/analyze",
                data={
                    "files": (BytesIO(csv.encode("utf-8")), "self_test.csv"),
                    "area_label": "EXE 自检观测范围",
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            assert uploaded.status_code == 302, (
                f"FIRMS upload HTTP {uploaded.status_code}"
            )
            task_url = uploaded.headers["Location"]
            assert task_url.startswith("/tasks/"), task_url
            task_id = task_url.rstrip("/").rsplit("/", 1)[-1]
            task_page = client.get(task_url)
            assert task_page.status_code == 200
            assert "EXE 自检观测范围" in task_page.get_data(as_text=True)
            checks.append("task-scoped FIRMS upload and result page")

            stage = "DOCX export with spatial map"
            exported = client.get(f"/tasks/{task_id}/report.docx")
            assert exported.status_code == 200, (
                f"DOCX export HTTP {exported.status_code}"
            )
            assert exported.data[:2] == b"PK"
            document = Document(BytesIO(exported.data))
            paragraphs = "\n".join(p.text for p in document.paragraphs)
            table_content = "\n".join(
                cell.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
            )
            for phrase in (
                "空间位置与火点分布",
                "优先核查位置与建议",
                "吉林",
            ):
                assert phrase in paragraphs, f"DOCX missing: {phrase}"
            assert "实测点 124.12000°E" in table_content
            assert "位置 1" in table_content
            assert len(document.inline_shapes) >= 1
            checks.append("DOCX report, real point, GeoJSON join and embedded map")

            stage = "sandbox persistence"
            from fire_monitor.user_data_paths import desktop_runtime_dir
            assert (desktop_runtime_dir() / "fire_monitor.sqlite").is_file()
            assert (
                desktop_runtime_dir() / "map_background" / "reference_basemap.json"
            ).is_file()
            checks.append("persistent paths isolated in temporary directory")

        outcome = {
            "ok": True,
            "checks": checks,
            "sample_observations": 3,
            "status": "release core self-test passed",
        }
    except Exception as exc:
        outcome = {
            "ok": False,
            "checks": checks,
            "stage": stage,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        for name, original in original_env.items():
            if original is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = original
        # Report is outside the sandbox and is read by the build verifier.
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(outcome, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return 1
    return 0 if outcome["ok"] else 1
