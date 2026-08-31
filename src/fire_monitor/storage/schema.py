"""SQLite 数据库结构定义。

本模块声明数据库结构，不执行数据库连接或业务操作。

设计原则：
1. 保留现有 FIRMS 主动火点与 MCD64A1 火烧迹地数据表；
2. 增加分析任务、输入文件和行政边界版本记录；
"""

from __future__ import annotations


BASE_SCHEMA = """
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
    FOREIGN KEY(import_run_id)
        REFERENCES import_runs(id)
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
    FOREIGN KEY(import_run_id)
        REFERENCES import_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_burned_pixel_date_region
ON burned_pixels(burned_date, region_name);

CREATE TABLE IF NOT EXISTS boundary_sets (
    boundary_set_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT,
    version TEXT,
    sha256 TEXT,
    geometry_crs TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_tasks (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    analysis_start TEXT,
    analysis_end TEXT,
    status TEXT NOT NULL,
    boundary_set_id TEXT,
    software_version TEXT NOT NULL,
    assessment_mode TEXT,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY(boundary_set_id)
        REFERENCES boundary_sets(boundary_set_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_tasks_created_at
ON analysis_tasks(created_at);

CREATE INDEX IF NOT EXISTS idx_analysis_tasks_status
ON analysis_tasks(status);

CREATE TABLE IF NOT EXISTS input_files (
    id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,
    file_role TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    source_agency TEXT,
    product_name TEXT,
    product_version TEXT,
    processing_class TEXT,
    date_start TEXT,
    date_end TEXT,
    crs TEXT,
    validation_status TEXT NOT NULL DEFAULT 'pending',
    validation_message TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id)
        REFERENCES analysis_tasks(task_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_input_files_task_id
ON input_files(task_id);

CREATE INDEX IF NOT EXISTS idx_input_files_sha256
ON input_files(sha256);
"""


CURRENT_SCHEMA_VERSION = 1