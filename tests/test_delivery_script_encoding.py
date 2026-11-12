"""Guard the Windows PowerShell 5.1 release path and EXE reuse policy."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_windows_powershell_reads_chinese_release_paths():
    path = ROOT / "scripts" / "finalize_windows_delivery.ps1"
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), (
        "Windows PowerShell 5.1 reads UTF-8 without BOM as a local code page, "
        "corrupting the Chinese onedir/EXE path after a successful build"
    )
    script = raw.decode("utf-8-sig")
    assert "农业秸秆焚烧区域火点检测与分析平台" in script
    assert 'Join-Path $appDir ($name + ".exe")' in script
    assert "EXE missing:" in script


def test_package_only_reuses_verified_binary_without_recompiling():
    script = (
        ROOT / "scripts" / "finalize_windows_delivery.ps1"
    ).read_text(encoding="utf-8-sig")
    assert "[switch] $PackageOnly" in script
    assert "if ($PackageOnly)" in script
    assert "git diff --name-only $builtSourceCommit $head" in script
    assert "The application source changed since the EXE was built" in script
    assert "scripts/verify_windows_bundle.py --app-dir $appDir" in script
    assert "scripts/check_frozen_exe.py --app-dir $appDir" in script
    assert "if (-not (Test-Path -LiteralPath $exe -PathType Leaf))" in script
    assert "Built application commit: $builtSourceCommit" in script
    assert "Delivery script commit: $head" in script
    assert 'Compress-Archive -LiteralPath $appDir' in script
    assert "Get-FileHash -LiteralPath $zipPath" in script
