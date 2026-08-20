"""面向本地部署的 SQLite 数据库。

数据模型有意区分两类观测：
1. active_fire_observations：FIRMS 主动火点观测记录；
2. burned_pixels：火烧迹地产品判定为烧毁的栅格像元。

两者不能互相替代，系统也不会把烧毁像元数写成官方主动火点数。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    level TEXT NOT NULL DEFAULT 'city',
    geometry_json TEXT NOT NULL,
    source TEXT,
    version TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY,
    data_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    stored_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS active_fire_observations (
    id INTEGER PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    acquired_date TEXT NOT NULL,
    acquired_time TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    region_name TEXT,
    firms_source TEXT NOT NULL,
    instrument TEXT,
    satellite TEXT,
    confidence TEXT,
    frp REAL,
    scan REAL,
    track REAL,
    quality_rule TEXT,
    import_run_id INTEGER,
    FOREIGN KEY(import_run_id) REFERENCES import_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_active_fire_date_region
ON active_fire_observations(acquired_date, region_name);

CREATE TABLE IF NOT EXISTS burned_pixels (
    id INTEGER PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    burned_date TEXT NOT NULL,
    doy INTEGER,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    region_name TEXT,
    cell_area_km2 REAL NOT NULL,
    source_product TEXT NOT NULL,
    raster_name TEXT,
    qa_value INTEGER,
    import_run_id INTEGER,
    FOREIGN KEY(import_run_id) REFERENCES import_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_burned_pixel_date_region
ON burned_pixels(burned_date, region_name);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    """轻量、可复制的本地数据存储。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
        with self.connect() as conn:
            conn.executescript(SCHEMA)

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
