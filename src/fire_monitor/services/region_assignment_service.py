from __future__ import annotations


class RegionAssignmentService:
    """
    烧毁像元行政区归属服务。

    将 burned_pixels 中的经纬度
    匹配到行政区域。
    """

    def __init__(
        self,
        database,
        spatial_service,
    ):
        self.database = database
        self.spatial_service = spatial_service


    def assign_regions(
        self,
        pixel_ids: list[int] | None = None,
    ) -> int:
        """
        为烧毁像元绑定行政区。

        返回：
        成功匹配数量
        """

        count = 0

        pixels = (
            self.database
            .list_burned_pixels(
                pixel_ids
            )
        )


        for pixel in pixels:

            region_name = (
                self.spatial_service
                .locate_region(
                    longitude=(
                        pixel["longitude"]
                    ),
                    latitude=(
                        pixel["latitude"]
                    ),
                )
            )


            if region_name:

                self.database.update_burned_pixel_region(
                    pixel["id"],
                    region_name,
                )

                count += 1


        return count