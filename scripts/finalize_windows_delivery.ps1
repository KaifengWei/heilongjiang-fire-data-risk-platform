param(
  [string] $CoverSource = "",
  [switch] $PackageOnly,
  [string] $BuiltCommit = ""
)
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
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is unavailable in this PowerShell process. Run the script using & from the original activated (fire-monitor) PowerShell prompt, not powershell -File." }
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

  $builtSourceCommit = $head
  if ($PackageOnly) {
    # Reuse an EXE that has already passed the frozen workflow.  Only
    # release scripts/docs may differ between that build and current HEAD.
    if ($CoverSource.Trim()) { throw "-CoverSource cannot be used with -PackageOnly." }
    if (-not $BuiltCommit.Trim()) {
      throw "-PackageOnly requires -BuiltCommit <commit of the successful EXE build>."
    }
    $resolved = & git rev-parse --verify $BuiltCommit
    if ($LASTEXITCODE -ne 0 -or -not $resolved) {
      throw "Unrecognized -BuiltCommit: $BuiltCommit"
    }
    $builtSourceCommit = ($resolved | Select-Object -First 1).Trim()
    & git merge-base --is-ancestor $builtSourceCommit $head
    if ($LASTEXITCODE -ne 0) {
      throw "The built commit must be an ancestor of the current branch."
    }
    $changes = @(& git diff --name-only $builtSourceCommit $head)
    if ($LASTEXITCODE -ne 0) { throw "Cannot compare built and delivery source." }
    $allowed = @(
      "scripts/finalize_windows_delivery.ps1",
      "docs/DELIVERY_HANDOFF.md",
      "docs/windows_exe_acceptance.md",
      "tests/test_delivery_script_encoding.py"
    )
    foreach ($changedFile in $changes) {
      if ($allowed -notcontains $changedFile) {
        throw "The application source changed since the EXE was built ($changedFile); rebuild rather than package an outdated binary."
      }
    }
    Write-Host "[1/4] Recheck previously built EXE: $builtSourceCommit"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
      throw "Previously built EXE does not exist: $exe"
    }
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
      throw "Conda is required to verify the existing EXE."
    }
    & conda run --no-capture-output -n fire-monitor python scripts/verify_windows_bundle.py --app-dir $appDir
    if ($LASTEXITCODE -ne 0) { throw "Existing EXE bundle resource check failed." }
    & conda run --no-capture-output -n fire-monitor python scripts/check_frozen_exe.py --app-dir $appDir
    if ($LASTEXITCODE -ne 0) { throw "Existing EXE failed the frozen workflow smoke test." }
  } else {
    Write-Host "[1/4] Run all tests, build EXE, verify bundle and frozen workflow"
    # Git and Conda may be functions only present in the activated shell.
    $buildScript = Join-Path $root "scripts\build_and_check_exe.ps1"
    if ($CoverSource.Trim()) {
      & $buildScript -CoverSource $CoverSource
    } else {
      & $buildScript
    }
    if ($LASTEXITCODE -ne 0) { throw "Build or EXE smoke test failed; no release ZIP created." }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "EXE missing: $exe" }
  }

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
Built application source commit: $builtSourceCommit
Delivery script commit: $head
Manual checklist in source: docs/windows_exe_acceptance.md
"@
  $utf8 = New-Object System.Text.UTF8Encoding($true)
  [System.IO.File]::WriteAllText((Join-Path $appDir "交付与使用说明.txt"), $guide, $utf8)

  Write-Host "[3/4] Zip the entire onedir, retaining the root application folder"
  $releaseDir = Join-Path $root "release"
  New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
  $base = $name + "_" + $builtSourceCommit.Substring(0, 9) + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + "_Windows"
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
Built application commit: $builtSourceCommit
Delivery script commit: $head
Built: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
EXE SHA256: $((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash)
ZIP SHA256: $((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash)
Source tests: validated in original build; frozen EXE smoke test: PASSED
Windows GUI, real-data weather and Word pagination acceptance: PENDING
"@
  [System.IO.File]::WriteAllText($manifestPath, $manifest, $utf8)
  Write-Host "DELIVERY ZIP: $zipPath"
  Write-Host "CHECKSUM: $manifestPath"
  Write-Host "EXE: $exe"
}
finally { Pop-Location }
