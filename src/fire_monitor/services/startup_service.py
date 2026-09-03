from __future__ import annotations

from pathlib import Path


class StartupService:
    """
    软件启动初始化服务。

    当前负责：
    1. 检查行政区基础数据
    2. 自动导入默认GeoJSON

    不负责：
    - 空间计算
    - 风险评估
    - 业务分析
    """

    def __init__(
        self,
        database,
        region_service,
        default_region_file: str | Path,
    ):
        self.database = database
        self.region_service = region_service
        self.default_region_file = Path(
            default_region_file
        )


    def initialize_default_regions(
        self,
    ) -> int:
        """
        初始化默认行政区数据。

        返回：
        导入数量
        """

        existing = (
            self.database.list_regions()
        )

        if existing:
            return 0


        if not self.default_region_file.exists():
            return 0


        return (
            self.region_service
            .import_geojson(
                self.default_region_file,
                source=(
                    "builtin"
                ),
                version=(
                    "1.0"
                ),
            )
        )