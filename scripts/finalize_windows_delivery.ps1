param([string] $CoverSource = "")
# Full Windows delivery: run existing checks, package complete onedir, hash.
# Never touch persisted %LOCALAPPDATA% user records or uploaded data.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$name = "农业秸秆焚烧区域火点检测与分析平台"
$branchExpected = "feature/regional-ui-consolidation-v1"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$appDir = Join-Path $root ("dist\" + $name)
$exe = Join-Path $appDir ($name + ".exe")
Push-Location $root
try {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git command unavailable." }
  $branch = (& git branch --show-current).Trim()
  if ($LASTEXITCODE -ne 0 -or $branch -ne $branchExpected) { throw "Expected branch: $branchExpected; found: $branch" }
  & git diff --quiet
  if ($LASTEXITCODE -ne 0) { throw "Uncommitted tracked files detected; preserve them first." }
  & git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) { throw "Staged local modifications detected; preserve them first." }
  $head = (& git rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0) { throw "Cannot read source commit." }
  $remote = (& git rev-parse ("origin/" + $branchExpected)).Trim()
  if ($LASTEXITCODE -ne 0 -or $head -ne $remote) {
    throw "Local source is not at fetched remote HEAD. Fetch and fast-forward first."
  }

  Write-Host "[1/4] Run all tests, build EXE, verify bundle and frozen workflow"
  $buildArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 (Join-Path $root "scripts\build_and_check_exe.ps1"))
  if ($CoverSource.Trim()) { $buildArgs += @("-CoverSource", $CoverSource) }
  & powershell.exe @buildArgs
  if ($LASTEXITCODE -ne 0) { throw "Build or EXE smoke test failed; no release ZIP created." }
  if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "EXE missing: $exe" }

  Write-Host "[2/4] Write included usage guide"
  $guide = @"
$name
Run the EXE inside the extracted COMPLETE folder (include _internal).
User records, uploaded CSV, offline map: %LOCALAPPDATA%\HeilongjiangFireMonitor
Do NOT delete that persistent user data directory when upgrading.
Modules: FIRMS CSV, map zoom and filtering, grid/time analyses, land cover,
historical/forecast weather, Word reports.
Code tests + frozen EXE self-test: verified by build script.
Actual Windows GUI, real CSV, weather network and Word layout: manual acceptance PENDING.
Git source commit: $head
Manual checklist in source: docs/windows_exe_acceptance.md
"@
  $utf8 = New-Object System.Text.UTF8Encoding($true)
  [System.IO.File]::WriteAllText((Join-Path $appDir "交付与使用说明.txt"), $guide, $utf8)

  Write-Host "[3/4] Zip the entire onedir, retaining the root application folder"
  $releaseDir = Join-Path $root "release"
  New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
  $base = $name + "_" + $head.Substring(0, 9) + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + "_Windows"
  $zipPath = Join-Path $releaseDir ($base + ".zip")
  $manifestPath = Join-Path $releaseDir ($base + "_SHA256.txt")
  Compress-Archive -LiteralPath $appDir -DestinationPath $zipPath -CompressionLevel Optimal -ErrorAction Stop
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
  try {
    $found = @($archive.Entries | Where-Object {
      $_.FullName.Replace("\", "/").EndsWith("/" + $name + ".exe")
    })
    if ($found.Count -ne 1) { throw "ZIP does not contain exactly one expected EXE." }
  }
  finally { $archive.Dispose() }

  Write-Host "[4/4] Write hashes and acceptance status"
  $manifest = @"
Product: $name
Branch: $branchExpected
Commit: $head
Built: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
EXE SHA256: $((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash)
ZIP SHA256: $((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash)
Source tests + frozen EXE smoke test: PASSED
Windows GUI, real-data weather and Word pagination acceptance: PENDING
"@
  [System.IO.File]::WriteAllText($manifestPath, $manifest, $utf8)
  Write-Host "DELIVERY ZIP: $zipPath"
  Write-Host "CHECKSUM: $manifestPath"
  Write-Host "EXE: $exe"
}
finally { Pop-Location }
