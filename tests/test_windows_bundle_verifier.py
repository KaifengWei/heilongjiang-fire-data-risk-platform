"""Release bundle checks run with synthetic directories on CI."""

from scripts.verify_windows_bundle import REQUIRED_FILES, missing_bundle_items


def _fake_bundle(folder):
    internal = folder / "_internal"
    for relative in REQUIRED_FILES:
        file = internal / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"present")
    (internal / "gdal_data").mkdir(parents=True)
    (internal / "data" / "regions").mkdir(parents=True)
    (folder / (folder.name + ".exe")).write_bytes(b"exe")


def test_bundle_verification_detects_missing_runtime_components(tmp_path):
    folder = tmp_path / "农业秸秆焚烧区域火点检测与分析平台"
    _fake_bundle(folder)
    assert missing_bundle_items(folder) == []
    missing_path = folder / "_internal" / "proj_data" / "proj.db"
    missing_path.unlink()
    assert "_internal/proj_data/proj.db" in missing_bundle_items(folder)
    missing_path.write_bytes(b"restored")
    (folder / "_internal" / "static" / "product.js").unlink()
    assert "_internal/static/product.js" in missing_bundle_items(folder)


def test_bundle_verification_requires_onedir_support_folder(tmp_path):
    folder = tmp_path / "dist" / "app"
    folder.mkdir(parents=True)
    assert missing_bundle_items(folder) == ["_internal/"]
