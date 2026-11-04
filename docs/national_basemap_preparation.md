# 全国真实底图数据接入（1:100 万公众版）

正式软件名称仍为 **农业秸秆焚烧区域火点检测与分析平台**，产品定位仍为“本软件面向农业相关区域的 FIRMS 火点观测分析”。

全国真实地理轮廓来自用户实际取得的矢量数据，不由程序合成行政轮廓。地图显示仅用于火点观测位置参考。

## 1. 数据取得

官方发布机构：国家基础地理信息中心。资料入口：

- 全国 1:100 万公众版基础地理信息数据（2021）：https://www.webmap.cn/commres.do?method=result100W
- 天地图数据资源平台：https://cloudcenter.tianditu.gov.cn/dataSource
- 标准地图服务：https://bzdt.tianditu.gov.cn/

根据官方说明，数据是 **77 幅**标准分幅，采用 **CGCS2000 地理坐标系**，境界与政区的面图层名称是 **BOUA**。数据整体内容涉及各类要素，处理时只读取 BOUA 行政区面，并非把农田/道路/地貌数据混在一起。

请通过官方服务取得你有权使用的数据，并在电脑上解压原始文件。下载可能要求登录注册。此功能不绕过访问权限，也不随软件自带未取得发布权限的全国行政轮廓。

## 2. 在同一个原项目内转换

使用原有 Windows Conda 环境，无需新增 Git 仓库或软件工程目录。在 PowerShell 中：

```powershell
cd D:\GitHubProjects\heilongjiang-straw-burning-monitor
conda activate fire-monitor

# 先检查解压后的数据图层
python scripts/prepare_official_basemap.py --input "D:\数据下载\全国1比100万" --inspect

# 从完整的 77 幅中抽取 BOUA，转换成真实 WGS84 面轮廓并合并
python scripts/prepare_official_basemap.py --input "D:\数据下载\全国1比100万" --layer BOUA --expected-sources 77 --source "国家基础地理信息中心：1:100万公众版基础地理信息数据（2021）" --output "D:\数据下载\firms_reference.geojson" --install --confirm-usage-rights
```

如果个别分幅没有 BOUA 图层，可经检查后增加 `--allow-missing-layer`；程序会逐项列出。没有明确来源坐标参考系的文件，会拒绝转换；只有确认原始坐标系后才可使用 `--source-epsg 4490`。

脚本使用 GDAL 读取 GDB / Shapefile / GeoPackage；将数据正确转换至 WGS84 经纬度，拼接面要素并去除内部区县分割，最终只保留用于定位的轻量轮廓。不将简化结果用于行政区归属判定。若官方数据以 `.gdb.zip` 提供，先解压成 `.gdb` 文件夹，再运行。

`--expected-sources 77` 仅校验数量，**不等于自动证明全国覆盖或内容合规**。必须核实图幅清单、海岛、边界与实际范围，确认其完整性以及正式发布条件。

## 3. EXE 中使用

- 使用 `--install` 后将底图写入 Windows 当前用户的 `%LOCALAPPDATA%\AgriculturalFirmsAnalysis\map_background\reference_basemap.json`，与软件既有离线地图路径相同，重新打包不会丢失。
- 也可以只指定 `--output` 生成 `firms_reference.geojson`，再在分析结果的“导入离线地图（GeoJSON）”功能中安装。
- 结果仍按实际 FIRMS 经度、纬度绘制，并能从“观测范围”切换至“轮廓全貌”；未取得数据的区域继续显示坐标网格。

官方说明强调：原始矢量数据不是最终地图，公开发布前应遵守地图管理与审核要求。**本功能的实现不代表已经取得官方底图、完成全国数据安装或通过公开地图审核**。
