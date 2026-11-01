# Windows EXE 打包与验收（方案 B）

适用分支：`feature/regional-ui-consolidation-v1`。正式产品名称：**农业秸秆焚烧区域火点检测与分析平台**。

## 打包前

首页右侧使用已经确认的地球遥感 WebP 封面。源代码仓库**未包含**该图片，请使用此前已确定、授权且真实存在的文件，放到 `static/images/home_earth_orbit.webp`。缺失、过小或格式不符时，PyInstaller 构建将直接报错，避免发布残缺的 EXE。请勿用随机占位图替代用户已选定的视觉资源。

先在 Windows 的项目目录中激活既有 `fire-monitor` Conda 环境，关闭正在运行的旧 EXE，再执行：

```powershell
conda activate fire-monitor
powershell -ExecutionPolicy Bypass -File ".\scripts\build_and_check_exe.ps1" -CoverSource "D:\实际路径\home_earth_orbit.webp"
```

若图片已经在 `static/images` 下，则省略 `-CoverSource`。脚本执行 Python 全量测试、可用时执行 JavaScript 语法检查、运行 PyInstaller 并核对 EXE 及打包后封面资源。最新 CI 记录不代替本机执行结果。

## 本机 EXE 验收记录

以下各项必须使用新打包 EXE **实际操作**后勾选；当前不能视为已完成。

- [ ] EXE 冷启动成功，首页封面真实显示，封面无已要求删除的上下说明文字；左侧文字、图标、版本清晰可读
- [ ] 首页进入“开始分析”，页面保持独立的浅色业务风格，教程不重复弹出
- [ ] 未安装 GeoJSON 的情况下导入 FIRMS CSV，分析成功并形成一条记录
- [ ] 一份 CSV 包含多个坐标区域时不丢有效观测；结果按真实经纬度网格分组，不虚构行政区
- [ ] 选填区域名称不影响空间筛选；选填经纬度矩形时仅保留矩形内观测
- [ ] 农事规则/土地覆盖缺失或不匹配时明确显示证据不足，不能认定发生秸秆焚烧
- [ ] 历史与天气数据只在本次区域适用时显示，不套用旧省份的数据
- [ ] 结果页与 Word 报告的数量、观测坐标跨度、区域标签、相关性结论一致
- [ ] 旧分析记录能够重新打开；关闭并再次启动 EXE 后，历史记录仍在
- [ ] 断网后重复打开 EXE、查看本地记录与导出既有 Word 报告；允许实时气象请求失败但不得破坏本地功能
- [ ] 复制整套 `dist/农业秸秆焚烧区域火点检测与分析平台/` 至另一台兼容 Windows 电脑运行，验证 GDAL、PROJ、GEOS 及桌面窗口依赖

## 验收原则

CI 的 pytest / JavaScript 成功仅证明代码层回归检查通过；Windows GUI、数据目录持久化、下载路径和运行组件必须通过以上实测。不要删除 `dist` 文件夹中的依赖文件后单独分发 EXE。

正式提交软著材料前，依据实际实测结果、截图和 Word 报告修订说明书；`main` 分支继续保留稳定版本。
