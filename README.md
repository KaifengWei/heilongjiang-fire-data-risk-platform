# Heilongjiang Fire Data Risk Platform

黑龙江省火点数据检测与风险评估平台（本地单机版，开发中）

[![tests](https://github.com/KaifengWei/heilongjiang-fire-data-risk-platform/actions/workflows/tests.yml/badge.svg)](https://github.com/KaifengWei/heilongjiang-fire-data-risk-platform/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

平台的正式定位是：**用户从官方平台自行下载原始数据并提交，软件自动完成文件校验、栅格处理、面积计算、行政区统计、重分类、制图、表格导出和有明确规则来源的等级分析。**

本项目将两类遥感信息放入同一个、可追溯的本地查询系统：

1. **主动火点观测记录**：来自 NASA FIRMS 等产品的卫星热异常记录；
2. **火烧迹地像元和面积**：来自 MCD64A1 等火烧迹地产品的 `burndate` 栅格统计。

它们有不同的物理意义，系统会分表保存、分图层显示、分别统计，避免将“烧毁像元数”错误地称为“官方火点数”。

详细的软件边界与文件提交规范见 [docs/05_平台边界与文件提交规范.md](docs/05_平台边界与文件提交规范.md)，风险评级口径见 [docs/06_风险评级方法与口径.md](docs/06_风险评级方法与口径.md)。

## 当前真实可运行功能（v0.1）

- 导入省、市、县级 GeoJSON 行政区边界；
- 导入本地 FIRMS CSV，按既定质量规则筛选，并按行政区赋值；
- 提供开发者可选的 FIRMS Area API 导入命令，但它不属于首版用户主流程，网页端不会索取 MAP_KEY；
- 导入已有的“烧毁像元明细 CSV”，接续历史验证成果；
- 从 MCD64 月度 `burndate` GeoTIFF 中提取烧毁像元、烧毁日期和实际网格面积；
- 用 SQLite 保存原始导入批次、来源、空间记录和统计结果；
- 按区域与日期查询主动火点观测记录数、烧毁像元数和火烧迹地面积；
- 在本地浏览器页面以红色主动火点层、绿色烧毁像元层分开显示；
- 导出当前筛选条件下的 CSV 摘要与逐日统计；
- 提供单元测试，覆盖空间落区、FIRMS 质量规则、MCD64 日期/面积辅助算法和查询接口。

当前网页还没有完成“浏览器上传—任务进度—结果包下载”闭环，现阶段通过命令导入本地文件。该闭环、风险规则引擎和 HDF-EOS 直读属于 v1.0 下一阶段，不能在现阶段软著材料中写成已经实现。

## 不作出的不实表述

- “主动火点观测记录数”不是独立火灾事件数；同一处燃烧可被多个卫星或多次过境观测。
- `scan × track` 是主动火点观测足迹，不是烧毁面积，系统不把它累计为火烧迹地面积。
- MCD64A1 烧毁像元面积是遥感产品估算值；农田小斑块、云覆盖、时相与产品本身的识别能力都会造成漏检或边界误差。
- 未导入对应 QA 图层时，系统会记录“QA 未提供”，不会声称已经完成 QA 筛选。

## 推荐技术路线

| 层级 | 当前选择 | 原因 |
|---|---|---|
| 数据与算法 | Python 3.11 + Pandas + NumPy + GDAL/OGR | 当前已有 TIF、Shapefile/GeoJSON、CSV 工作流和 Windows GIS 环境可直接复用。 |
| 本地服务 | Flask | 现有五市原型已验证可运行；结构轻、Windows 启动简单，便于软著源码与功能一一对应。 |
| 数据库 | SQLite（v1.0） | 单机、可随软件交付、便于保留导入批次和历史查询；多用户部署时可迁移到 PostgreSQL/PostGIS。 |
| 前端 | 原生 HTML/CSS/JavaScript + Canvas | 不需要 Node/Vue 构建链，离线本地可运行；页面和地图图层功能都在仓库内。 |
| 官方接口 | FIRMS Area API（可选） | 支持按时间、区域和传感器下载主动火点 CSV；MAP_KEY 只保留在服务器/本机环境。 |

这不是否定 Vue 或 Java，而是当前数据处理的核心在 Python/GDAL，且目标是先形成一套能在 Windows 本地演示、可打包、可核验、可写软著的产品。后续若出现多人并发、移动端或省级长期在线服务需求，再把查询 API 接到 Vue 前端与 PostGIS 即可，不需要推翻数据模型。

## 环境安装

MCD64 TIF 导入需要 GDAL，推荐使用 Conda：

```powershell
conda env create -f environment.yml
conda activate fire-monitor
```

如果只需要查看已导入数据、导入 CSV 或启动页面，也可创建普通 Python 环境并安装基础依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 启动页面

```powershell
python main.py serve
```

浏览器打开 <http://127.0.0.1:5060>。也可双击 `启动系统.bat`。

## 使用现有资料初始化

以下命令只读取现有资料，不会改写原始 TIF、CSV 或边界文件。路径请替换为你自己的实际位置。

### 1. 导入五市边界

若使用包含五个城市的 GADM GeoJSON：

```powershell
python main.py init-regions `
  --geojson "C:\路径\five_cities_gadm.geojson" `
  --name-field "NL_NAME_2" `
  --source "GADM 行政区边界" `
  --version "4.1"
```

若用一个市由多个区县组成的 GeoJSON，则为每市重复一次：

```powershell
python main.py init-regions `
  --geojson "C:\路径\佳木斯市.geojson" `
  --region-name "佳木斯市" `
  --source "本地市级行政区边界"
```

### 2. 导入 FIRMS 主动火点 CSV

```powershell
python main.py import-firms-csv `
  --file "C:\路径\official_five_cities_quality_filtered_202511.csv" `
  --source "FIRMS_202511_QUALITY" `
  --region-column "City"
```

默认质量规则沿用现有项目的记录：VIIRS `confidence` 为 `n` / `h`，MODIS `confidence >= 30`。若输入文件已经是质量筛选结果，重复筛选应仍得到同一或更严格的集合；需要保留原始全部记录时加 `--keep-all`。

`--region-column City` 仅适用于该 CSV 的 `City` 字段已经由**同一版本行政区边界**赋值的情况，可避免重复进行空间落区。对来自 FIRMS Area API 的原始 CSV 或边界版本不确定的数据，应省略该参数，让系统按当前导入 GeoJSON 重新落区。

### 3. 导入当前 2025-11 已验证的烧毁像元明细

```powershell
python main.py import-burned-csv `
  --file "C:\路径\我方烧毁像元_面积明细.csv" `
  --product "2025-11 已验证烧毁像元成果"
```

### 4. 从 MCD64 月度 TIF 重新提取烧毁像元与面积

```powershell
python main.py import-mcd64 `
  --tif "C:\路径\MCD64monthly.A2026060.Win16.061.burndate.tif" `
  --product "MCD64A1 C6.1"
```

文件名中的 `AYYYYDDD` 用于识别该月起始年积日；系统只把该月的 `burndate > 0` 值写入，并将每一像元转换成对应的实际烧毁日期。对于当前 EPSG:4326 TIF，面积按球面经纬度网格实际面积计算。

## 可选：在线获取官方 FIRMS 主动火点

将 MAP_KEY 保存在本机环境变量中，**不要提交到 GitHub**：

```powershell
$env:FIRMS_MAP_KEY = "你的本机密钥"
python main.py fetch-firms `
  --source "VIIRS_SNPP_NRT" `
  --bbox "121.0,43.4,135.2,53.6" `
  --start "2026-03-01" `
  --end "2026-03-31"
```

FIRMS Area API 按边界框、日期范围和传感器返回主动火点 CSV。代码自动分成不超过 5 天的请求批次，避免把密钥暴露到浏览器端。接口文档见 [NASA FIRMS API](https://firms.modaps.eosdis.nasa.gov/api/) 和 [FIRMS Python 教程](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html)。

## 项目结构

```text
src/fire_monitor/
  core/        # GeoJSON 空间落区、FIRMS 规范化、MCD64 TIF 面积计算
  services/    # 边界、CSV、TIF、FIRMS API 导入服务
  storage/     # SQLite 表结构、导入批次和查询
  app.py       # 本地查询与导出 API
templates/     # 浏览器页面
static/        # 页面样式和 Canvas 图层绘制
docs/          # 技术路线、数据口径、软著源码对应表和发布清单
tests/         # 可重复单元测试
```

## 与软著材料的关系

系统功能、字段、算法说明和源码模块对应关系已经放在 [docs/03_软著功能与源代码对应表.md](docs/03_软著功能与源代码对应表.md)。撰写申请材料时应只写已经实现并可演示的功能；“实时预警”“手机端”“模型识别”等尚未实现的功能只能写入后续计划，不能写入软件功能说明。

## 开源前检查

发布远程 GitHub 仓库前，请完成 [docs/04_开源发布与数据合规清单.md](docs/04_开源发布与数据合规清单.md)。特别注意：真实 MAP_KEY、原始大体积 TIF、个人或机构未授权数据、以及不确定再分发权限的边界数据都不应直接上传。

当前公开版本的实际验收结果见 [docs/07_版本验收记录_0.1.0.md](docs/07_版本验收记录_0.1.0.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。
