"""FIRMS 主动火点观测及来源记录持久化。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fire_monitor.storage.database import (
    Database,
    utc_now,
)


@dataclass(frozen=True)
class FirmsStoreResult:
    """一次 FIRMS 数据库存储结果。"""

    input_rows: int
    inserted_observations: int
    existing_observations: int
    source_records_added: int
    source_records_existing: int
    preferred_source_updates: int


def should_replace_preferred_source(
    current: str | None,
    incoming: str | None,
) -> bool:
    """判断新来源是否应成为观测主记录的首选来源。

    当前策略：
    1. SP 优先于非 SP；
    2. 已经是 SP 时，不被 NRT/RT/URT 覆盖；
    3. UNKNOWN 可以被已识别来源替换；
    4. NRT/RT/URT 之间暂不声明科学优先级。

    这是平台的数据管理策略，不宣称为 NASA 官方排序。
    """

    current_class = (
        current or "UNKNOWN"
    ).upper()

    incoming_class = (
        incoming or "UNKNOWN"
    ).upper()

    if current_class == incoming_class:
        return False

    if incoming_class == "SP":
        return current_class != "SP"

    if current_class == "SP":
        return False

    if (
        current_class == "UNKNOWN"
        and incoming_class != "UNKNOWN"
    ):
        return True

    return False


class FirmsRepository:
    """管理规范化 FIRMS 观测和来源历史。"""

    def __init__(
        self,
        database: Database,
    ):
        self.database = database
        self.database.initialize()

    def store_rows(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        import_run_id: int | None = None,
    ) -> FirmsStoreResult:
        """保存规范化 FIRMS 记录。

        dedupe_key 必须是 canonical observation key。
        """

        rows = list(rows)

        inserted_observations = 0
        existing_observations = 0
        source_records_added = 0
        source_records_existing = 0
        preferred_source_updates = 0

        with self.database.connect() as conn:
            for row in rows:
                canonical_key = row[
                    "dedupe_key"
                ]

                existing = conn.execute(
                    """
                    SELECT
                        id,
                        processing_class
                    FROM active_fire_observations
                    WHERE dedupe_key = ?
                    """,
                    (canonical_key,),
                ).fetchone()

                if existing is None:
                    cursor = conn.execute(
                        """
                        INSERT INTO active_fire_observations(
                            dedupe_key,
                            acquired_date,
                            acquired_time,
                            latitude,
                            longitude,
                            region_name,
                            firms_source,
                            processing_class,
                            source_version,
                            instrument,
                            satellite,
                            confidence,
                            frp,
                            scan,
                            track,
                            quality_rule,
                            import_run_id
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            canonical_key,
                            row["acquired_date"],
                            row.get(
                                "acquired_time"
                            ),
                            row["latitude"],
                            row["longitude"],
                            row.get(
                                "region_name"
                            )
                            or row.get(
                                "source_region_name"
                            ),
                            row["firms_source"],
                            row.get(
                                "processing_class"
                            ),
                            row.get(
                                "source_version"
                            ),
                            row.get(
                                "instrument"
                            ),
                            row.get(
                                "satellite"
                            ),
                            row.get(
                                "confidence"
                            ),
                            row.get("frp"),
                            row.get("scan"),
                            row.get("track"),
                            row.get(
                                "quality_rule"
                            ),
                            import_run_id,
                        ),
                    )

                    observation_id = int(
                        cursor.lastrowid
                    )

                    inserted_observations += 1

                else:
                    observation_id = int(
                        existing["id"]
                    )

                    existing_observations += 1

                    if should_replace_preferred_source(
                        existing[
                            "processing_class"
                        ],
                        row.get(
                            "processing_class"
                        ),
                    ):
                        conn.execute(
                            """
                            UPDATE active_fire_observations
                            SET
                                firms_source = ?,
                                processing_class = ?,
                                source_version = ?,
                                confidence = ?,
                                frp = ?,
                                scan = ?,
                                track = ?,
                                quality_rule = ?,
                                import_run_id = ?
                            WHERE id = ?
                            """,
                            (
                                row[
                                    "firms_source"
                                ],
                                row.get(
                                    "processing_class"
                                ),
                                row.get(
                                    "source_version"
                                ),
                                row.get(
                                    "confidence"
                                ),
                                row.get("frp"),
                                row.get("scan"),
                                row.get("track"),
                                row.get(
                                    "quality_rule"
                                ),
                                import_run_id,
                                observation_id,
                            ),
                        )

                        preferred_source_updates += 1

                source_key = row[
                    "source_record_key"
                ]

                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO
                    active_fire_observation_sources(
                        observation_id,
                        source_record_key,
                        firms_source,
                        processing_class,
                        source_version,
                        confidence,
                        frp,
                        scan,
                        track,
                        quality_rule,
                        import_run_id,
                        created_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        observation_id,
                        source_key,
                        row[
                            "firms_source"
                        ],
                        row.get(
                            "processing_class"
                        )
                        or "UNKNOWN",
                        row.get(
                            "source_version"
                        ),
                        row.get(
                            "confidence"
                        ),
                        row.get("frp"),
                        row.get("scan"),
                        row.get("track"),
                        row.get(
                            "quality_rule"
                        ),
                        import_run_id,
                        utc_now(),
                    ),
                )

                if cursor.rowcount == 1:
                    source_records_added += 1
                else:
                    source_records_existing += 1

        return FirmsStoreResult(
            input_rows=len(rows),
            inserted_observations=(
                inserted_observations
            ),
            existing_observations=(
                existing_observations
            ),
            source_records_added=(
                source_records_added
            ),
            source_records_existing=(
                source_records_existing
            ),
            preferred_source_updates=(
                preferred_source_updates
            ),
        )

    def get_observation(
        self,
        canonical_key: str,
    ) -> dict[str, Any] | None:
        """读取一条主观测记录。"""

        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM active_fire_observations
                WHERE dedupe_key = ?
                """,
                (canonical_key,),
            ).fetchone()

        return (
            dict(row)
            if row is not None
            else None
        )

    def list_sources(
        self,
        canonical_key: str,
    ) -> list[dict[str, Any]]:
        """读取某条观测保留的全部来源记录。"""

        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.*
                FROM
                    active_fire_observation_sources s
                JOIN
                    active_fire_observations o
                ON
                    s.observation_id = o.id
                WHERE
                    o.dedupe_key = ?
                ORDER BY
                    s.id
                """,
                (canonical_key,),
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]