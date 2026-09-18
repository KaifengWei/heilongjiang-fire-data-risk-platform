$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot


Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Fire Monitor Windows Build" -ForegroundColor Cyan
Write-Host " PyInstaller onedir mode" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""


# ---------------------------------------------------------
# Resolve the active Conda environment explicitly.
# Do not rely on PATH because a child PowerShell may resolve
# Python from the Anaconda base environment.
# ---------------------------------------------------------

if (-not $env:CONDA_PREFIX) {
    throw "CONDA_PREFIX is not available. Activate the fire-monitor environment first."
}


$CondaEnvName = Split-Path $env:CONDA_PREFIX -Leaf

if ($CondaEnvName -ne "fire-monitor") {
    throw "Wrong Conda environment: $CondaEnvName. Activate fire-monitor first."
}


$PythonExe = Join-Path $env:CONDA_PREFIX "python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable was not found: $PythonExe"
}


Write-Host "[1/6] Checking build environment..." -ForegroundColor Yellow

Write-Host "Conda environment:"
Write-Host $env:CONDA_PREFIX

Write-Host "Python executable:"
Write-Host $PythonExe

& $PythonExe --version

if ($LASTEXITCODE -ne 0) {
    throw "Python environment check failed."
}


$PythonPrefix = & $PythonExe -c "import sys; print(sys.prefix)"

if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Python sys.prefix."
}

Write-Host "Python prefix:"
Write-Host $PythonPrefix


Write-Host ""
Write-Host "[2/6] Checking obsolete pathlib backport..." -ForegroundColor Yellow

$HasPathlib = & $PythonExe -c "import importlib.metadata as m; print(any((d.metadata.get('Name') or '').lower() == 'pathlib' for d in m.distributions()))"

if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect installed Python packages."
}

if ($HasPathlib.Trim() -eq "True") {

    Write-Host "Obsolete pathlib backport detected." -ForegroundColor Yellow
    Write-Host "Removing pathlib from the build environment..." -ForegroundColor Yellow

    & $PythonExe -m pip uninstall -y pathlib

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to remove obsolete pathlib backport."
    }

} else {

    Write-Host "No pathlib backport found. OK." -ForegroundColor Green
}


Write-Host ""
Write-Host "[3/6] Installing desktop build dependencies..." -ForegroundColor Yellow

& $PythonExe -m pip install -r ".\requirements-desktop.txt"

if ($LASTEXITCODE -ne 0) {
    throw "Desktop build dependency installation failed."
}


Write-Host ""
Write-Host "[4/6] Running regression tests..." -ForegroundColor Yellow

& $PythonExe -m pytest -q

if ($LASTEXITCODE -ne 0) {
    throw "Regression tests failed. Build stopped."
}


Write-Host ""
Write-Host "[5/6] Cleaning previous build artifacts..." -ForegroundColor Yellow

if (Test-Path ".\build") {
    Remove-Item ".\build" -Recurse -Force
}

if (Test-Path ".\dist") {
    Remove-Item ".\dist" -Recurse -Force
}


Write-Host ""
Write-Host "[6/6] Running PyInstaller..." -ForegroundColor Yellow

& $PythonExe -m PyInstaller `
    --clean `
    --noconfirm `
    ".\fire_monitor.spec"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}


if (-not (Test-Path ".\dist")) {
    throw "Build finished but dist directory was not created."
}


$ExeCandidates = @()

Get-ChildItem ".\dist" -Directory | ForEach-Object {

    $ExeCandidates += Get-ChildItem `
        -Path $_.FullName `
        -Filter "*.exe" `
        -File `
        -ErrorAction SilentlyContinue
}


$Exe = $ExeCandidates |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1


if ($null -eq $Exe) {
    throw "Build finished but the application EXE was not found."
}


Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " BUILD SUCCESS" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

Write-Host ""
Write-Host "Application EXE:" -ForegroundColor Cyan
Write-Host $Exe.FullName

Write-Host ""
Write-Host "EXE size:" -ForegroundColor Cyan
Write-Host ("{0:N2} MB" -f ($Exe.Length / 1MB))

Write-Host ""
Write-Host "Distribution directory:" -ForegroundColor Cyan
Write-Host $Exe.Directory.FullName

Write-Host ""
Write-Host "Start the EXE from this directory for final validation." -ForegroundColor Yellow