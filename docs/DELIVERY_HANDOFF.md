# 农业秸秆焚烧区域火点检测与分析平台 — 集成交付与一次性验收

交付形式：Windows 桌面 EXE，Flask + pywebview，PyInstaller onedir。
交付仓库：https://github.com/KaifengWei/heilongjiang-fire-data-risk-platform
交付分支：feature/regional-ui-consolidation-v1

## 本版已包含的主要功能

1. NASA FIRMS CSV 导入、清洗、任务保存与历史记录管理。
2. Canvas 地图、真实火点、离线边界、地图连续缩放、拖动、日期和网格定位。
3. 0.25° 观测网格数量与占比、单日高值与累计热点位置比较、约 5 km 跨日重复观测统计。
4. 实际 MCD12Q1 土地覆盖匹配数量与耕地或混合植被背景，不把背景视为已证实秸秆焚烧。
5. NOAA GFS 24/48/72 小时天气、NASA POWER 历史天气、逐日气象与火点对照。
6. 任务期空间、时间、天气、地表证据联合分析与操作性结果。
7. Word 图文报告，含真实位置、统计清单、时间走势图、FRP、地表和气象分析。

## 一次性获取完整 EXE 与可分发 ZIP

请关闭旧 EXE；保留项目原目录内已批准的首页 WebP 文件，保留真实 CSV 和现有用户数据。

在 Windows Anaconda PowerShell 中执行：

    cd D:\GitHubProjects\heilongjiang-straw-burning-monitor
    git fetch origin
    git merge --ff-only origin/feature/regional-ui-consolidation-v1
    git rev-list --left-right --count HEAD...origin/feature/regional-ui-consolidation-v1
    Set-ExecutionPolicy -Scope Process Bypass -Force
    & ".\scripts\finalize_windows_delivery.ps1"

同步完成后第三条应输出 0 0。必须在当前已激活的 Anaconda PowerShell 会话内使用 `&` 直接调用脚本，不要再用 `powershell -File` 创建新子窗口；新进程可能无法继承该会话的 Git、Conda 命令或函数。`Set-ExecutionPolicy -Scope Process Bypass` 只对当前会话有效。发生冲突时停止处理，不使用 reset --hard 或 git clean。
当首页 WebP 不在 static/images/home_earth_orbit.webp 时，可传入 -CoverSource 和实际图片路径。

交付脚本先运行完整源码回归测试、JavaScript 语法检查、PyInstaller 打包、运行资源核验及最新 EXE 本体的独立无界面自检。只有这些步骤都通过，才会生成以下文件：

- dist/农业秸秆焚烧区域火点检测与分析平台/农业秸秆焚烧区域火点检测与分析平台.exe
- release/农业秸秆焚烧区域火点检测与分析平台_<提交>_<构建时间>_Windows.zip
- 同名前缀的 _SHA256.txt 校验文件

发布或复制时必须保留整个目录及 _internal，不能只复制 EXE。

## 集中验收清单（同一次构建执行）

- [ ] 启动 EXE，首页与功能栏正常，退出重启后历史分析记录仍在。
- [ ] 打开已经导入的真实 1,591 条观测、28 个有观测日期的记录，数量、日期、地图与 Word 一致。
- [ ] 地图可绘制火点和实际轮廓；Ctrl + 滚轮、加减按钮、拖动、全貌切换与具体网格/日期定位正常。
- [ ] 三个重点网格、单日高值、跨日重复网格均与 CSV 数据一致，单日高值热点和累计热点不混淆。
- [ ] 土地覆盖部分匹配时，准确呈现有证据的观测条数、农业背景和未匹配条数；不编造地表。
- [ ] 历史 NASA POWER 天气、逐日对照、火点/天气/地表联合证据可用；近期任务 GFS 范围符合真实观测位置。
- [ ] 导出 Word 包含空间地图、完整日期走势图、真实重点网格与实测坐标、FRP、土地覆盖、天气分析及联合结论。
- [ ] Word A4 分页合理；中文宋体、西文 Times New Roman，无乱码；图注、表头和跨页内容完整，数据无重复堆砌。
- [ ] 断网时已保存任务仍能打开；已有天气缓存正常复用，未缓存天气不会破坏本地分析。
- [ ] 将完整 ZIP 解压到兼容 Windows 环境，可运行而不依赖原工程目录。

运行中的源码自动测试与 EXE 无界面自检，不等于 GUI 与 Word 实际排版已经完成验收。未通过的项目应记录真实复现步骤，并集中修复，不逐项反复打包。

## 数据与发布规则

用户记录、上传文件和离线地图持久保存在 %LOCALAPPDATA%\HeilongjiangFireMonitor。
交付脚本不清除该目录；升级 EXE 时也不删除。
main 分支仍作为稳定版本保留，集成版本只在原仓库既有重构分支内维护。
正式发布、软著截图和说明书仅依据已通过的实际验收结果。
