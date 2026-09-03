from __future__ import annotations

from shapely.geometry import Point, shape


class SpatialService:
    """
    空间归属查询服务。

    根据经纬度判断所属行政区。
    """

    def __init__(self, database):
        self.database = database

    def locate_region(
        self,
        longitude: float,
        latitude: float,
    ) -> str | None:
        """
        根据坐标返回行政区名称。
        """

        point = Point(
            longitude,
            latitude,
        )

        regions = self.database.list_regions()

        for region in regions:
            polygon = shape(
                region["geometry"]
            )

            if polygon.covers(point):
                return region["name"]

            if polygon.covers(point):
                return region["name"]

        return None