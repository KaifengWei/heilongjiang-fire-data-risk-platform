"""面向本地部署的 SQLite 数据库。

数据模型中的两类观测：
1. active_fire_observations：FIRMS 主动火点观测记录；
2. burned_pixels：火烧迹地产品判定为烧毁的栅格像元。

烧毁像元数不等同于官方主动火点数。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .migrations import apply_migrations


def utc_now() -> str:
    """返回不包含微秒的 UTC ISO 8601 时间。"""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


class Database:
    """轻量、可复制的本地数据存储。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """初始化数据库并执行增量迁移。"""

        with self.connect() as conn:
            apply_migrations(conn)

    def create_analysis_task(
        self,
        *,
        task_id: str,
        name: str,
        software_version: str,
        analysis_start: str | None = None,
        analysis_end: str | None = None,
        boundary_set_id: str | None = None,
        assessment_mode: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建一个新的分析任务。"""

        created_at = utc_now()

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_tasks(
                    task_id,
                    name,
                    analysis_start,
                    analysis_end,
                    status,
                    boundary_set_id,
                    software_version,
                    assessment_mode,
                    parameters_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'created', ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    name,
                    analysis_start,
                    analysis_end,
                    boundary_set_id,
                    software_version,
                    assessment_mode,
                    json.dumps(
                        parameters or {},
                        ensure_ascii=False,
                    ),
                    created_at,
                ),
            )

        task = self.get_analysis_task(task_id)

        if task is None:
            raise RuntimeError(
                f"分析任务创建后无法读取：{task_id}"
            )

        return task

    def get_analysis_task(
        self,
        task_id: str,
    ) -> dict[str, Any] | None:
        """读取一个分析任务。"""

        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    task_id,
                    name,
                    analysis_start,
                    analysis_end,
                    status,
                    boundary_set_id,
                    software_version,
                    assessment_mode,
                    parameters_json,
                    created_at,
                    started_at,
                    completed_at,
                    error_message
                FROM analysis_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result["parameters"] = json.loads(
            result.pop("parameters_json")
        )

        return result

    def list_analysis_tasks(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按创建时间倒序读取分析任务。"""

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    task_id,
                    name,
                    analysis_start,
                    analysis_end,
                    status,
                    boundary_set_id,
                    software_version,
                    assessment_mode,
                    parameters_json,
                    created_at,
                    started_at,
                    completed_at,
                    error_message
                FROM analysis_tasks
                ORDER BY created_at DESC, task_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        tasks: list[dict[str, Any]] = []

        for row in rows:
            item = dict(row)
            item["parameters"] = json.loads(
                item.pop("parameters_json")
            )
            tasks.append(item)

        return tasks

    def update_analysis_task_status(
        self,
        task_id: str,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        """更新分析任务状态。"""

        allowed_statuses = {
            "created",
            "validating",
            "ready",
            "running",
            "completed",
            "failed",
        }

        if status not in allowed_statuses:
            raise ValueError(
                f"不支持的任务状态：{status}"
            )

        now = utc_now()

        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT task_id, started_at
                FROM analysis_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

            if existing is None:
                raise KeyError(
                    f"分析任务不存在：{task_id}"
                )

            started_at = existing["started_at"]
            completed_at = None

            if (
                status == "running"
                and started_at is None
            ):
                started_at = now

            if status in {
                "completed",
                "failed",
            }:
                completed_at = now

            conn.execute(
                """
                UPDATE analysis_tasks
                SET
                    status = ?,
                    started_at = ?,
                    completed_at = ?,
                    error_message = ?
                WHERE task_id = ?
                """,
                (
                    status,
                    started_at,
                    completed_at,
                    error_message,
                    task_id,
                ),
            )

    def register_input_file(
        self,
        *,
        task_id: str,
        file_role: str,
        original_filename: str,
        sha256: str,
        size_bytes: int,
        stored_path: str | None = None,
        source_agency: str | None = None,
        product_name: str | None = None,
        product_version: str | None = None,
        processing_class: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        crs: str | None = None,
        validation_status: str = "pending",
        validation_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """登记分析任务使用的输入文件。"""

        if size_bytes < 0:
            raise ValueError(
                "size_bytes 不能小于 0"
            )

        with self.connect() as conn:
            task = conn.execute(
                """
                SELECT task_id
                FROM analysis_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

            if task is None:
                raise KeyError(
                    f"分析任务不存在：{task_id}"
                )

            cursor = conn.execute(
                """
                INSERT INTO input_files(
                    task_id,
                    file_role,
                    original_filename,
                    stored_path,
                    sha256,
                    size_bytes,
                    source_agency,
                    product_name,
                    product_version,
                    processing_class,
                    date_start,
                    date_end,
                    crs,
                    validation_status,
                    validation_message,
                    metadata_json,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    task_id,
                    file_role,
                    original_filename,
                    stored_path,
                    sha256,
                    size_bytes,
                    source_agency,
                    product_name,
                    product_version,
                    processing_class,
                    date_start,
                    date_end,
                    crs,
                    validation_status,
                    validation_message,
                    json.dumps(
                        metadata or {},
                        ensure_ascii=False,
                    ),
                    utc_now(),
                ),
            )

            return int(cursor.lastrowid)

    def list_input_files(
        self,
        task_id: str,
    ) -> list[dict[str, Any]]:
        """读取分析任务登记的输入文件。"""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    task_id,
                    file_role,
                    original_filename,
                    stored_path,
                    sha256,
                    size_bytes,
                    source_agency,
                    product_name,
                    product_version,
                    processing_class,
                    date_start,
                    date_end,
                    crs,
                    validation_status,
                    validation_message,
                    metadata_json,
                    created_at
                FROM input_files
                WHERE task_id = ?
                ORDER BY id
                """,
                (task_id,),
            ).fetchall()

        result: list[dict[str, Any]] = []

        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(
                item.pop("metadata_json")
            )
            result.append(item)

        return result

    def upsert_regions(self, regions: Iterable[dict[str, Any]]) -> int:
        values = []
        for region in regions:
            values.append(
                (
                    region["name"],
                    region.get("level", "city"),
                    json.dumps(region["geometry"], ensure_ascii=False),
                    region.get("source"),
                    region.get("version"),
                    utc_now(),
                )
            )
        if not values:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO regions(name, level, geometry_json, source, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    level=excluded.level,
                    geometry_json=excluded.geometry_json,
                    source=excluded.source,
                    version=excluded.version,
                    created_at=excluded.created_at
                """,
                values,
            )
        return len(values)

    def list_regions(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name, level, geometry_json, source, version FROM regions ORDER BY name"
            ).fetchall()
        return [
            {
                "name": row["name"],
                "level": row["level"],
                "geometry": json.loads(row["geometry_json"]),
                "source": row["source"],
                "version": row["version"],
            }
            for row in rows
        ]

    def start_import(
        self, data_kind: str, source_ref: str, metadata: dict[str, Any] | None = None
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO import_runs(data_kind, source_ref, started_at, status, metadata_json)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (data_kind, source_ref, utc_now(), json.dumps(metadata or {}, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def finish_import(
        self,
        run_id: int,
        input_count: int,
        stored_count: int,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            if metadata is None:
                conn.execute(
                    """
                    UPDATE import_runs
                    SET completed_at=?, status=?, input_count=?, stored_count=?
                    WHERE id=?
                    """,
                    (utc_now(), status, input_count, stored_count, run_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE import_runs
                    SET completed_at=?, status=?, input_count=?, stored_count=?, metadata_json=?
                    WHERE id=?
                    """,
                    (
                        utc_now(),
                        status,
                        input_count,
                        stored_count,
                        json.dumps(metadata, ensure_ascii=False),
                        run_id,
                    ),
                )

    def fail_import(self, run_id: int, reason: str) -> None:
        self.finish_import(run_id, 0, 0, status="failed", metadata={"error": reason})

    def insert_active_fire_rows(self, rows: Iterable[dict[str, Any]], run_id: int) -> int:
        values = [
            (
                row["dedupe_key"],
                row["acquired_date"],
                row.get("acquired_time"),
                row["latitude"],
                row["longitude"],
                row.get("region_name"),
                row["firms_source"],
                row.get("instrument"),
                row.get("satellite"),
                row.get("confidence"),
                row.get("frp"),
                row.get("scan"),
                row.get("track"),
                row.get("quality_rule"),
                run_id,
            )
            for row in rows
        ]
        if not values:
            return 0
        with self.connect() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO active_fire_observations(
                    dedupe_key, acquired_date, acquired_time, latitude, longitude, region_name,
                    firms_source, instrument, satellite, confidence, frp, scan, track,
                    quality_rule, import_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return conn.total_changes - before

    def insert_burned_pixel_rows(self, rows: Iterable[dict[str, Any]], run_id: int) -> int:
        values = [
            (
                row["dedupe_key"],
                row["burned_date"],
                row.get("doy"),
                row["latitude"],
                row["longitude"],
                row.get("region_name"),
                row["cell_area_km2"],
                row["source_product"],
                row.get("raster_name"),
                row.get("qa_value"),
                run_id,
            )
            for row in rows
        ]
        if not values:
            return 0
        with self.connect() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO burned_pixels(
                    dedupe_key, burned_date, doy, latitude, longitude, region_name,
                    cell_area_km2, source_product, raster_name, qa_value, import_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return conn.total_changes - before

    @staticmethod
    def _filter_clause(
        date_column: str, region: str | None, start: str | None, end: str | None
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if region:
            clauses.append("region_name = ?")
            params.append(region)
        if start:
            clauses.append(f"{date_column} >= ?")
            params.append(start)
        if end:
            clauses.append(f"{date_column} <= ?")
            params.append(end)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def summary(self, region: str | None, start: str | None, end: str | None) -> dict[str, Any]:
        fire_clause, fire_params = self._filter_clause("acquired_date", region, start, end)
        burned_clause, burned_params = self._filter_clause("burned_date", region, start, end)
        with self.connect() as conn:
            active = conn.execute(
                f"SELECT COUNT(*) AS n FROM active_fire_observations{fire_clause}", fire_params
            ).fetchone()["n"]
            burned = conn.execute(
                f"SELECT COUNT(*) AS n, COALESCE(SUM(cell_area_km2), 0) AS area "
                f"FROM burned_pixels{burned_clause}",
                burned_params,
            ).fetchone()
            active_by_source = conn.execute(
                f"""
                SELECT firms_source, COUNT(*) AS count
                FROM active_fire_observations{fire_clause}
                GROUP BY firms_source ORDER BY firms_source
                """,
                fire_params,
            ).fetchall()
            burned_by_source = conn.execute(
                f"""
                SELECT source_product, COUNT(*) AS pixels,
                       COALESCE(SUM(cell_area_km2), 0) AS area_km2
                FROM burned_pixels{burned_clause}
                GROUP BY source_product ORDER BY source_product
                """,
                burned_params,
            ).fetchall()
        return {
            "region": region or "全部已导入区域",
            "start": start,
            "end": end,
            "active_fire_observation_count": int(active),
            "burned_pixel_count": int(burned["n"]),
            "burned_area_km2": round(float(burned["area"]), 6),
            "active_by_source": [dict(row) for row in active_by_source],
            "burned_by_source": [dict(row) for row in burned_by_source],
            "definitions": {
                "active_fire_observation_count": "FIRMS 等主动火点产品中的卫星观测记录数；不等于独立火灾事件数。",
                "burned_pixel_count": "火烧迹地产品中被判定为烧毁的栅格像元数；不等于官方主动火点数。",
                "burned_area_km2": "所选火烧迹地栅格像元的地表面积之和。",
            },
        }

    def daily_series(
        self, region: str | None, start: str | None, end: str | None
    ) -> list[dict[str, Any]]:
        fire_clause, fire_params = self._filter_clause("acquired_date", region, start, end)
        burned_clause, burned_params = self._filter_clause("burned_date", region, start, end)
        with self.connect() as conn:
            fire_rows = conn.execute(
                f"""
                SELECT acquired_date AS date, COUNT(*) AS active_fire_observation_count
                FROM active_fire_observations{fire_clause}
                GROUP BY acquired_date ORDER BY acquired_date
                """,
                fire_params,
            ).fetchall()
            burned_rows = conn.execute(
                f"""
                SELECT burned_date AS date, COUNT(*) AS burned_pixel_count,
                       COALESCE(SUM(cell_area_km2), 0) AS burned_area_km2
                FROM burned_pixels{burned_clause}
                GROUP BY burned_date ORDER BY burned_date
                """,
                burned_params,
            ).fetchall()
        series: dict[str, dict[str, Any]] = {}
        for row in fire_rows:
            series.setdefault(row["date"], {"date": row["date"], "active_fire_observation_count": 0, "burned_pixel_count": 0, "burned_area_km2": 0.0})
            series[row["date"]]["active_fire_observation_count"] = int(row["active_fire_observation_count"])
        for row in burned_rows:
            series.setdefault(row["date"], {"date": row["date"], "active_fire_observation_count": 0, "burned_pixel_count": 0, "burned_area_km2": 0.0})
            series[row["date"]]["burned_pixel_count"] = int(row["burned_pixel_count"])
            series[row["date"]]["burned_area_km2"] = round(float(row["burned_area_km2"]), 6)
        return [series[key] for key in sorted(series)]

    def map_records(
        self, region: str | None, start: str | None, end: str | None, limit: int
    ) -> dict[str, Any]:
        fire_clause, fire_params = self._filter_clause("acquired_date", region, start, end)
        burned_clause, burned_params = self._filter_clause("burned_date", region, start, end)
        with self.connect() as conn:
            fire_total = conn.execute(
                f"SELECT COUNT(*) AS n FROM active_fire_observations{fire_clause}", fire_params
            ).fetchone()["n"]
            burned_total = conn.execute(
                f"SELECT COUNT(*) AS n FROM burned_pixels{burned_clause}", burned_params
            ).fetchone()["n"]
            fire_rows = conn.execute(
                f"""
                SELECT longitude, latitude, acquired_date AS date, region_name, firms_source,
                       instrument, confidence, frp
                FROM active_fire_observations{fire_clause}
                ORDER BY acquired_date, longitude, latitude LIMIT ?
                """,
                [*fire_params, limit],
            ).fetchall()
            burned_rows = conn.execute(
                f"""
                SELECT longitude, latitude, burned_date AS date, region_name, source_product,
                       cell_area_km2
                FROM burned_pixels{burned_clause}
                ORDER BY burned_date, longitude, latitude LIMIT ?
                """,
                [*burned_params, limit],
            ).fetchall()
        return {
            "active_fire": {"total": int(fire_total), "points": [dict(row) for row in fire_rows]},
            "burned_pixels": {"total": int(burned_total), "points": [dict(row) for row in burned_rows]},
        }

    def region_feature_collection(self, selected_region: str | None = None) -> dict[str, Any]:
        features = []
        for region in self.list_regions():
            if selected_region and region["name"] != selected_region:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "name": region["name"],
                        "level": region["level"],
                        "source": region["source"],
                        "version": region["version"],
                    },
                    "geometry": region["geometry"],
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def data_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            regions = conn.execute("SELECT COUNT(*) AS n FROM regions").fetchone()["n"]
            active = conn.execute("SELECT COUNT(*) AS n, MIN(acquired_date) AS first, MAX(acquired_date) AS last FROM active_fire_observations").fetchone()
            burned = conn.execute("SELECT COUNT(*) AS n, MIN(burned_date) AS first, MAX(burned_date) AS last FROM burned_pixels").fetchone()
            imports = conn.execute(
                """
                SELECT data_kind, source_ref, status, input_count, stored_count, completed_at, metadata_json
                FROM import_runs ORDER BY id DESC LIMIT 20
                """
            ).fetchall()
        return {
            "regions": int(regions),
            "active_fire": {"count": int(active["n"]), "start": active["first"], "end": active["last"]},
            "burned_pixels": {"count": int(burned["n"]), "start": burned["first"], "end": burned["last"]},
            "imports": [
                {**dict(row), "metadata": json.loads(row["metadata_json"])} for row in imports
            ],
        }
