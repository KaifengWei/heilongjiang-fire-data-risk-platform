"""Release archive must match the Windows bundle, not just contain one EXE."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from scripts.verify_release_archive import verify_release_archive
from scripts.verify_windows_bundle import REQUIRED_FILES


def _make_bundle(tmp_path):
    app = tmp_path / "dist" / "农业秸秆焚烧区域火点检测与分析平台"
    (app / "_internal" / "gdal_data").mkdir(parents=True)
    (app / "_internal" / "data" / "regions").mkdir(parents=True)
    for rel in REQUIRED_FILES:
        path = app / "_internal" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime " + rel.encode("utf-8"))
    (app / (app.name + ".exe")).write_bytes(b"successful-self-tested-exe")
    (app / "_internal" / "gdal_data" / "header.txt").write_bytes(b"GDAL test")
    (app / "_internal" / "data" / "regions" / "metadata.txt").write_bytes(b"source")
    return app


def _zip(app, tmp_path, *, missing=None, extra=None, root_name=None):
    target = tmp_path / "release.zip"
    root = root_name or app.name
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in app.rglob("*"):
            if path.is_file():
                relative = path.relative_to(app).as_posix()
                if relative == missing:
                    continue
                archive.write(path, arcname=root + "/" + relative)
        if extra:
            archive.writestr(root + "/" + extra, b"not-from-built-bundle")
    return target


def test_release_zip_contains_exact_verified_bundle(tmp_path):
    app = _make_bundle(tmp_path)
    archive = _zip(app, tmp_path)
    result = verify_release_archive(app, archive)
    assert result["files"] == len(list(p for p in app.rglob("*") if p.is_file()))
    assert result["required"] == len(REQUIRED_FILES) + 1
    assert len(result["zip_sha256"]) == 64


def test_release_zip_rejects_missing_visual_asset_and_native_runtime(tmp_path):
    app = _make_bundle(tmp_path)
    for rel in (
        "_internal/static/result_console.css",
        "_internal/static/weather_context.js",
        "_internal/proj_data/proj.db",
    ):
        archive = _zip(app, tmp_path, missing=rel)
        with pytest.raises(ValueError, match="ZIP and built folder differ"):
            verify_release_archive(app, archive)


def test_release_zip_rejects_wrong_root_or_unexpected_files(tmp_path):
    app = _make_bundle(tmp_path)
    archive = _zip(app, tmp_path, root_name="other")
    with pytest.raises(ValueError, match="outside its application folder"):
        verify_release_archive(app, archive)
    archive = _zip(app, tmp_path, extra="unexpected.txt")
    with pytest.raises(ValueError, match="ZIP and built folder differ"):
        verify_release_archive(app, archive)


def test_release_zip_rejects_changed_exe_even_if_same_size(tmp_path):
    app = _make_bundle(tmp_path)
    archive = _zip(app, tmp_path)
    exe = app / (app.name + ".exe")
    original = exe.read_bytes()
    exe.write_bytes(b"changed-exe!" .ljust(len(original), b"!"))
    assert exe.stat().st_size == len(original)
    with pytest.raises(ValueError, match="ZIP contents differ from built file"):
        verify_release_archive(app, archive)


def test_release_zip_rejects_invalid_archive(tmp_path):
    app = _make_bundle(tmp_path)
    path = tmp_path / "broken.zip"
    path.write_bytes(b"not-a-zip")
    with pytest.raises(ValueError, match="Invalid ZIP archive"):
        verify_release_archive(app, path)
