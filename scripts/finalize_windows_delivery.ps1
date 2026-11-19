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
      "scripts/verify_release_archive.py",
      "scripts/verify_windows_bundle.py",
      "docs/DELIVERY_HANDOFF.md",
      "docs/windows_exe_acceptance.md",
      "docs/SOFTWARE_COPYRIGHT_HANDOFF.md",
      "tests/test_delivery_script_encoding.py",
      "tests/test_release_archive_verification.py",
      "tests/test_windows_bundle_verifier.py"
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
  # Check every ZIP member, CRC, path and critical resource against the
  # exact onedir build that passed the frozen EXE core self-test.
  & conda run --no-capture-output -n fire-monitor python scripts/verify_release_archive.py --app-dir $appDir --zip-path $zipPath
  if ($LASTEXITCODE -ne 0) { throw "Release archive integrity failed; do not distribute ZIP." }

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
Release ZIP integrity (all files, CRC and critical file SHA256): PASSED
Windows GUI, real-data weather and Word pagination acceptance: PENDING
"@
  [System.IO.File]::WriteAllText($manifestPath, $manifest, $utf8)
  # A version-pinned worksheet for one concentrated hands-on pass.
  # All checkboxes deliberately start unchecked: CI never implies GUI PASS.
  $acceptancePath = Join-Path $releaseDir ($base + "_Windows验收记录.md")
  $checklist = @"
# $name — Windows EXE 实机验收记录

EXE 构建源码：$builtSourceCommit
交付脚本源码：$head
分发 ZIP：$(Split-Path -Path $zipPath -Leaf)
ZIP SHA256：$((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash)
实际验收日期：待填写
执行环境（Windows版本、屏幕分辨率）：待填写
当前结论：**待实机验收**（源码测试、自检、ZIP核验不能代替GUI实测）

## 第一组：安装与历史数据
- [ ] A01 冷启动，首页及侧栏完整，界面在 1440×900 和 1100×700 下可操作
- [ ] A02 原有任务、离线底图和用户数据在关闭重启后仍保留
- [ ] A03 未安装行政区 GeoJSON 也能导入 FIRMS CSV；多坐标范围与选填矩形正确
- [ ] A04 用真实任务核对有效火点数量、观测日期及原始 CSV，无重复或漏点

## 第二组：地图及分析结果
- [ ] B01 真实火点和离线轮廓正常显示，缩放 +/−、Ctrl+滚轮、拖动、范围切换有效
- [ ] B02 日期筛选、首位网格定位、高值日热点、跨日重复位置操作有效
- [ ] B03 首位网格、前三网格与实际 CSV 的坐标、日期、数量对应
- [ ] B04 农业相关性仅使用已匹配 MCD12Q1 观测，真实分类缩略图与样本坐标对应
- [ ] B05 默认界面清晰简洁，详细统计可展开，窗口缩小后不溢出

## 第三组：天气与报告
- [ ] C01 历史任务 NASA POWER 与观测日期一致；近期任务 GFS 24/48/72h 对应实际位置
- [ ] C02 天气、地表与火点联合展示结果和已取得的数值一致，断网可读取已缓存记录
- [ ] C03 EXE 内 Word 下载可用，报告与页面观测数、网格、峰值日、地表和天气对应
- [ ] C04 Word 含真实地图、日期趋势和 FRP，A4 分页、宋体及 Times New Roman 无乱码

## 第四组：交付与持久化
- [ ] D01 将完整 ZIP 解压到新目录（非原工程目录）后可启动并完成导入与报告导出
- [ ] D02 校验本次 ZIP SHA256，与同前缀 _SHA256.txt 相符
- [ ] D03 断网打开已保存任务正常，原有 SQLite 记录/上传文件/安装的离线底图均不丢失
- [ ] D04 所有不通过项有截图、复现步骤及对应记录，不误标为已通过

## 验收结论
通过项目数：____ / 17
不通过项与复现记录：____________________________
对应截图/Word 文件名：__________________________
最终结论：待确认 / 通过 / 需修复
下一阶段：仅在以上必要项目完成实机验收后，按实际功能与截图更新软著说明书。

扩展测试口径见仓库 docs/windows_exe_acceptance.md。
"@
  [System.IO.File]::WriteAllText($acceptancePath, $checklist, $utf8)
  Write-Host "GUI ACCEPTANCE RECORD: $acceptancePath"
  Write-Host "DELIVERY ZIP: $zipPath"
  Write-Host "CHECKSUM: $manifestPath"
  Write-Host "EXE: $exe"
}
finally { Pop-Location }
