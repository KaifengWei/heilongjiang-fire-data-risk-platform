# 演示数据目录

为避免把用户的 MAP_KEY、完整 FIRMS 下载结果、原始 TIF 或行政边界许可状态不明的数据直接提交到 GitHub，本仓库不内置真实业务数据。

请按项目根目录 README 的“使用现有资料初始化”步骤，把本地真实数据导入 `data/runtime/fire_monitor.sqlite`。数据库、TIF、Shapefile 和私有 CSV 已被 `.gitignore` 排除，不会随代码上传。

单元测试会在临时目录中创建小型测试数据；它们只用于验证算法与接口，不代表任何真实火情。
