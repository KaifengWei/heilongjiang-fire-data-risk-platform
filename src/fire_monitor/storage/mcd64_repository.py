"""MCD64A1 烧毁像元规范存储与运行关系管理。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fire_monitor.storage.database import (
    Database,
    utc_now,
)


@dataclass(frozen=True)
class Mcd64StoreResult:
    """一次烧毁像元存储结果。"""

    input_rows: int
    inserted_pixels: int
    existing_pixels: int
    run_memberships_added: int
    run_memberships_existing: int


class Mcd64Repository:
    """管理规范烧毁像元及其处理运行关系。"""

    def __init__(
        self,
        database: Database,
    ):
        self.database = database
        self.database.initialize()

    def store_rows(
        self,
        rows: Iterable[
            dict[str, Any]
        ],
        *,
        import_run_id: int,
    ) -> Mcd64StoreResult:
        """保存已经完成 QA 与空间筛选的烧毁像元。

        canonical_key 用于判断烧毁像元本身是否已经存在。

        dedupe_key 仍保留具体栅格来源下的记录身份，
        用于兼容旧数据结构和来源追溯。
        """

        rows = list(rows)

        inserted_pixels = 0
        existing_pixels = 0

        run_memberships_added = 0
        run_memberships_existing = 0

        with self.database.connect() as conn:
            for row in rows:
                canonical_key = row.get(
                    "canonical_key"
                )

                if not canonical_key:
                    raise ValueError(
                        "MCD64A1 烧毁像元缺少 "
                        "canonical_key。"
                    )

                existing = conn.execute(
                    """
                    SELECT id
                    FROM burned_pixels
                    WHERE canonical_key = ?
                    """,
                    (
                        canonical_key,
                    ),
                ).fetchone()

                if existing is None:
                    cursor = conn.execute(
                        """
                        INSERT INTO burned_pixels(
                            dedupe_key,
                            canonical_key,
                            burned_date,
                            doy,
                            latitude,
                            longitude,
                            region_name,
                            cell_area_km2,
                            source_product,
                            raster_name,
                            qa_value,
                            import_run_id
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            row["dedupe_key"],
                            canonical_key,
                            row["burned_date"],
                            row.get("doy"),
                            row["latitude"],
                            row["longitude"],
                            row.get(
                                "region_name"
                            ),
                            row[
                                "cell_area_km2"
                            ],
                            row[
                                "source_product"
                            ],
                            row.get(
                                "raster_name"
                            ),
                            row.get(
                                "qa_value"
                            ),
                            import_run_id,
                        ),
                    )

                    burned_pixel_id = int(
                        cursor.lastrowid
                    )

                    inserted_pixels += 1

                else:
                    burned_pixel_id = int(
                        existing["id"]
                    )

                    existing_pixels += 1

                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO
                    burned_pixel_run_membership(
                        run_id,
                        burned_pixel_id,
                        created_at
                    )
                    VALUES (
                        ?, ?, ?
                    )
                    """,
                    (
                        import_run_id,
                        burned_pixel_id,
                        utc_now(),
                    ),
                )

                if cursor.rowcount == 1:
                    run_memberships_added += 1
                else:
                    run_memberships_existing += 1

        return Mcd64StoreResult(
            input_rows=len(rows),
            inserted_pixels=(
                inserted_pixels
            ),
            existing_pixels=(
                existing_pixels
            ),
            run_memberships_added=(
                run_memberships_added
            ),
            run_memberships_existing=(
                run_memberships_existing
            ),
        )

    def list_run_pixels(
        self,
        run_id: int,
    ) -> list[dict[str, Any]]:
        """读取某次处理运行实际接受的烧毁像元。"""

        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    p.*
                FROM
                    burned_pixel_run_membership m
                JOIN
                    burned_pixels p
                ON
                    m.burned_pixel_id = p.id
                WHERE
                    m.run_id = ?
                ORDER BY
                    p.burned_date,
                    p.longitude,
                    p.latitude
                """,
                (
                    run_id,
                ),
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]