param(
    [string] $CoverSource = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$productName = "农业秸秆焚烧区域火点检测与分析平台"
$coverPath = Join-Path $projectRoot "static\images\home_earth_orbit.webp"

Push-Location $projectRoot
try {
    if ($CoverSource.Trim()) {
        $sourcePath = (Resolve-Path -LiteralPath $CoverSource -ErrorAction Stop).Path
        if ($sourcePath -ne $coverPath) {
            New-Item -ItemType Directory -Path (Split-Path $coverPath -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $sourcePath -Destination $coverPath -Force
        }
    }

    if (-not (Test-Path -LiteralPath $coverPath -PathType Leaf)) {
        throw "Missing homepage asset: $coverPath. Run with -CoverSource pointing to the approved WebP."
    }
    if ((Get-Item -LiteralPath $coverPath).Length -lt 1024) {
        throw "Homepage WebP is too small to package: $coverPath"
    }
    $stream = [System.IO.File]::OpenRead($coverPath)
    try {
        $header = New-Object byte[] 12
        if ($stream.Read($header, 0, 12) -ne 12) {
            throw "Cannot read WebP header: $coverPath"
        }
        $fourcc = [System.Text.Encoding]::ASCII.GetString($header, 0, 4)
        $format = [System.Text.Encoding]::ASCII.GetString($header, 8, 4)
        if ($fourcc -ne "RIFF" -or $format -ne "WEBP") {
            throw "Incorrect WebP file signature: $coverPath"
        }
    }
    finally {
        $stream.Dispose()
    }

    # The PowerShell prompt can show (fire-monitor) while "python" still
    # resolves to Anaconda base. Always invoke the named Conda environment.
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        throw "Conda command not found. Open Anaconda PowerShell Prompt and run this script again."
    }
    Write-Host "[0/3] Verify the named fire-monitor Conda environment"
    & conda run --no-capture-output -n fire-monitor python -c "import sys; import shapely; from osgeo import gdal; import pandas; import docx; print('Python:', sys.executable); print('Shapely:', shapely.__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Conda environment fire-monitor is missing required packages or cannot start. Check: conda run -n fire-monitor python -c 'import shapely; from osgeo import gdal'"
    }

    Write-Host "[1/3] Run full Python tests"
    & conda run --no-capture-output -n fire-monitor python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Python regression tests failed." }

    Write-Host "[2/3] Check JavaScript syntax (when Node.js is installed)"
    if (Get-Command node -ErrorAction SilentlyContinue) {
        foreach ($js in @("static/product.js", "static/county_drilldown.js", "static/home.js")) {
            & node --check $js
            if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax failed: $js" }
        }
    }
    else {
        Write-Warning "Node.js is absent; JavaScript syntax is covered by GitHub Actions."
    }

    Write-Host "[3/3] Build the Windows desktop application"
    & conda run --no-capture-output -n fire-monitor python -m PyInstaller --clean --noconfirm fire_monitor.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $outputDir = Join-Path $projectRoot ("dist\" + $productName)
    $exePath = Join-Path $outputDir ($productName + ".exe")
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "Expected EXE not found: $exePath"
    }

    $packagedCovers = @(
        (Join-Path $outputDir "_internal\static\images\home_earth_orbit.webp"),
        (Join-Path $outputDir "static\images\home_earth_orbit.webp")
    )
    if (-not ($packagedCovers | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })) {
        throw "Build completed without the homepage image. Do not release this EXE."
    }
    # Check packaged assets and native spatial dependencies before success.
    Write-Host "[3/3] Verify bundled runtime and map resources"
    & conda run --no-capture-output -n fire-monitor python scripts/verify_windows_bundle.py --app-dir $outputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Windows EXE resource verification failed."
    }
    Write-Host "[4/4] Run packaged EXE core workflow without opening the GUI"
    & conda run --no-capture-output -n fire-monitor python scripts/check_frozen_exe.py --app-dir $outputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged Windows EXE failed its isolated smoke test."
    }

    Write-Host "Build verified: $exePath"
    Write-Host "Next: run the EXE and check the manual acceptance scenarios in docs/windows_exe_acceptance.md"
}
finally {
    Pop-Location
}
