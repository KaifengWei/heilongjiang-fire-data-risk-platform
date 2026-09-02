"""SQLite 数据库增量迁移。

迁移项目早期已经生成的数据库。
禁止通过 DROP TABLE 或删除用户数据的方式完成常规升级。
"""

from __future__ import annotations

import sqlite3

from .schema import BASE_SCHEMA, CURRENT_SCHEMA_VERSION


def _table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """返回指定数据表当前包含的字段名称。"""

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row[1] for row in rows}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    """字段不存在时执行 ALTER TABLE ADD COLUMN。"""

    columns = _table_columns(conn, table_name)

    if column_name in columns:
        return

    conn.execute(
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} {definition}"
    )


def apply_migrations(conn: sqlite3.Connection) -> None:
    """初始化或升级数据库到当前结构版本。"""

    conn.execute("PRAGMA foreign_keys = ON")

    # 首先保证所有基础表存在。
    conn.executescript(BASE_SCHEMA)

    current_version = int(
        conn.execute("PRAGMA user_version").fetchone()[0]
    )

    if current_version < 1:
        _add_column_if_missing(
            conn,
            "regions",
            "boundary_set_id",
            "TEXT",
        )

        _add_column_if_missing(
            conn,
            "import_runs",
            "task_id",
            "TEXT",
        )

        _add_column_if_missing(
            conn,
            "import_runs",
            "input_file_id",
            "INTEGER",
        )

        if current_version < 2:
            _add_column_if_missing(
                conn,
                "active_fire_observations",
                "processing_class",
                "TEXT",
            )

            _add_column_if_missing(
                conn,
                "active_fire_observations",
                "source_version",
                "TEXT",
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS
                    active_fire_observation_sources
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY,
                    observation_id
                    INTEGER
                    NOT
                    NULL,
                    source_record_key
                    TEXT
                    NOT
                    NULL
                    UNIQUE,
                    firms_source
                    TEXT
                    NOT
                    NULL,
                    processing_class
                    TEXT
                    NOT
                    NULL,
                    source_version
                    TEXT,
                    confidence
                    TEXT,
                    frp
                    REAL,
                    scan
                    REAL,
                    track
                    REAL,
                    quality_rule
                    TEXT,
                    import_run_id
                    INTEGER,
                    created_at
                    TEXT
                    NOT
                    NULL,
                    FOREIGN
                    KEY
                (
                    observation_id
                )
                    REFERENCES active_fire_observations
                (
                    id
                )
                    ON DELETE CASCADE,
                    FOREIGN KEY
                (
                    import_run_id
                )
                    REFERENCES import_runs
                (
                    id
                )
                    )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_active_fire_sources_observation
                    ON active_fire_observation_sources(
                    observation_id
                    )
                """
            )

        conn.execute(
            f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}"
        )

        conn.execute(
            f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}"
        )

