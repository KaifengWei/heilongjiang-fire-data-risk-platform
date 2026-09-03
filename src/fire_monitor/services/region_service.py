from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RegionService:
    """
    行政区空间数据管理服务。

    负责：
    1. 导入GeoJSON
    2. 写入regions表
    3. 查询已有区域
    """

    def __init__(
        self,
        database,
    ):
        self.database = database


    def import_geojson(
        self,
        path: str | Path,
        *,
        source: str | None = None,
        version: str | None = None,
    ) -> int:
        """
        导入行政区GeoJSON。
        """

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(
                f"文件不存在: {path}"
            )


        with path.open(
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)


        if data.get(
            "type"
        ) != "FeatureCollection":

            raise ValueError(
                "当前仅支持GeoJSON FeatureCollection"
            )


        regions = []


        for feature in data.get(
            "features",
            []
        ):

            properties = (
                feature.get(
                    "properties",
                    {}
                )
            )

            geometry = (
                feature.get(
                    "geometry"
                )
            )


            if geometry is None:
                continue


            name = (
                properties.get(
                    "name"
                )
                or properties.get(
                    "NAME"
                )
                or properties.get(
                    "NAME_1"
                )
            )


            if not name:
                raise ValueError(
                    "行政区缺少名称字段"
                )


            regions.append(
                {
                    "name": name,
                    "level": "city",
                    "geometry": geometry,
                    "source": source,
                    "version": version,
                }
            )


        return self.database.upsert_regions(
            regions
        )


    def list_regions(
        self,
    ):
        return self.database.list_regions()