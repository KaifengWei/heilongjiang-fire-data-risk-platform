# 农业秸秆焚烧区域火点检测与分析平台

**交付定位：** Windows 本地桌面端（Flask + pywebview + SQLite + GDAL/Shapely），处理用户导入的 NASA FIRMS 标准 CSV，开展用户声明区域内的火点观测时空分析（精确行政区落区可选）、农业秸秆焚烧相关性辅助判别和火点活动风险分析，并导出 Word 报告。

当前 P0 改造位于独立分支，不代表已经内置覆盖全国的行政区边界和土地覆盖数据。基于 MCD12Q1 2024 的土地覆盖分类用于耕地背景判断，须有实际栅格覆盖；地区农事时历需要有来源的规则文件，缺失时按证据不足处理。本软件不会凭 FIRMS 观测直接确定某次热异常必然是秸秆焚烧，也不生成虚假的火灾发生概率。

## 当前功能

- NASA FIRMS CSV 导入与校验、质量筛选、去重与任务记录；
- 普通分析直接保留整份 CSV 的有效观测，无需行政区边界；用户可填写区域名称及可选经纬度矩形；
- 支持安装来源明确、互不重叠的 GeoJSON 区域边界（高级功能）；
- 火点时空统计、峰值日期、跨日持续活跃位置、历史同期比较（具有可比数据时）；
- MCD12Q1 2024 土地覆盖背景及耕地相关性证据；
- 农事时段 JSON 配置、地区/作物/月份匹配、相关性等级与证据说明；
- NASA POWER 历史气象及 NOAA GFS 近期天气（有对应范围数据时；用户声明区域普通模式暂不借用旧地区气象数据）；
- 既有任务内火点活动风险关注分析、结果地图和 Word 报告导出。

## 运行与测试

```powershell
conda env create -f environment.yml
conda activate fire-monitor
python -m pytest -q
python main.py serve --port 5050
```

桌面 EXE 的打包配置在 `fire_monitor.spec`，以 Windows 实机重建和验收为准。

## 数据来源、范围与限制

- 火点观测：NASA FIRMS CSV；
- 土地覆盖：NASA MCD12Q1 V061 LC_Type1（现有 2024 年栅格，非全国连续覆盖）；
- 农事时历：用户填写有明确资料来源的地区、作物与适用月份；不自造全国统一默认时历；
- 分析区域：普通模式使用用户声明名称及真实观测点位置，不核验行政区归属；只有高级精确落区模式才使用已配置的真实边界；
- 分析分级：农业秸秆焚烧**相关性**与现有任务内火点**相对关注等级**分开统计，均不等于官方火灾检测结论或火灾概率。

详细 P0 判别口径见 [docs/agricultural_relevance_p0.md](docs/agricultural_relevance_p0.md)，边界库说明见 [docs/china_region_boundary_catalog.md](docs/china_region_boundary_catalog.md)。

## 开发原则

保留现有数据与稳定功能，独立测试分支推进改造，只有实际实现且经过验证的功能才写入最终使用说明书。未经授权的数据、密钥和全国行政区边界不打包发布。
