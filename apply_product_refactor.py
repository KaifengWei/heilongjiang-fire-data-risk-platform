from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd().resolve()

REQUIRED = [
    ROOT / "src/fire_monitor/app.py",
    ROOT / "src/fire_monitor/services/task_service.py",
    ROOT / "src/fire_monitor/services/statistics_service.py",
    ROOT / "src/fire_monitor/storage/schema.py",
    ROOT / "src/fire_monitor/storage/migrations.py",
    ROOT / "src/fire_monitor/storage/firms_repository.py",
    ROOT / "templates/index.html",
    ROOT / "templates/tasks.html",
    ROOT / "templates/task_detail.html",
    ROOT / "tests/test_tasks.py",
]

missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.is_file()]
if missing:
    raise SystemExit(
        "This script must be run from the project root. Missing:\n- "
        + "\n- ".join(missing)
    )

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = ROOT / "data/runtime" / f"product_refactor_backup_{stamp}"
backup_root.mkdir(parents=True, exist_ok=True)

TOUCH_EXISTING = [
    "src/fire_monitor/app.py",
    "src/fire_monitor/services/statistics_service.py",
    "src/fire_monitor/storage/schema.py",
    "src/fire_monitor/storage/migrations.py",
    "src/fire_monitor/storage/firms_repository.py",
    "templates/index.html",
    "templates/tasks.html",
    "templates/task_detail.html",
    "tests/test_tasks.py",
]

for rel in TOUCH_EXISTING:
    src = ROOT / rel
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one anchor, found {count}. "
            "No further changes were applied to this file."
        )
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# [新增] Auto analysis service: user selects files, software infers type/date,
# creates one isolated analysis record, validates, processes and reuses deduped
# observations through run membership.
# -----------------------------------------------------------------------------
AUTO_SERVICE = r'''"""自动识别用户上传文件并创建一次独立分析记录。"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fire_monitor.core.file_validation import (
    ValidationResult,
    validate_firms_csv,
    validate_mcd64_geotiff,
)
from fire_monitor.services.firms_processing_service import FirmsProcessingService
from fire_monitor.services.import_service import read_csv_with_fallback
from fire_monitor.services.mcd64_processing_service import Mcd64ProcessingService
from fire_monitor.services.readiness_service import ReadinessService
from fire_monitor.services.task_service import TaskService
from fire_monitor.services.validation_service import ValidationService


@dataclass(frozen=True)
class StagedUpload:
    path: Path
    original_filename: str


@dataclass(frozen=True)
class DetectedUpload:
    path: Path
    original_filename: str
    file_role: str
    validation: ValidationResult
    date_start: str | None
    date_end: str | None


@dataclass(frozen=True)
class AnalysisInspection:
    files: tuple[DetectedUpload, ...]
    analysis_scope: str
    analysis_start: str | None
    analysis_end: str | None
    task_name: str


class AutoAnalysisProcessingError(RuntimeError):
    def __init__(self, task_id: str, message: str):
        super().__init__(message)
        self.task_id = task_id


class AutoAnalysisService:
    """把“用户选择文件”转换为“自动识别并完成一次分析”。"""

    def __init__(
        self,
        *,
        task_service: TaskService,
        validation_service: ValidationService,
        readiness_service: ReadinessService,
        firms_processing_service: FirmsProcessingService,
        mcd64_processing_service: Mcd64ProcessingService,
    ):
        self.task_service = task_service
        self.validation_service = validation_service
        self.readiness_service = readiness_service
        self.firms_processing_service = firms_processing_service
        self.mcd64_processing_service = mcd64_processing_service

    @staticmethod
    def _firms_date_range(
        path: Path,
        validation: ValidationResult,
    ) -> tuple[str | None, str | None]:
        date_column = validation.metadata.get("date_column")
        if not date_column:
            return None, None

        frame = read_csv_with_fallback(path, low_memory=False)
        if date_column not in frame.columns:
            return None, None

        dates: list[str] = []
        for value in frame[date_column].tolist():
            raw = str(value).strip()[:10]
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                continue
            dates.append(parsed.isoformat())

        if not dates:
            return None, None

        return min(dates), max(dates)

    @staticmethod
    def _mcd64_role(filename: str) -> str:
        normalized = re.sub(
            r"[^a-z0-9]+",
            "_",
            filename.lower(),
        )
        tokens = {token for token in normalized.split("_") if token}

        if "qa" in tokens or "quality" in tokens:
            return "mcd64_qa"

        if (
            "burndate" in normalized
            or "burn_date" in normalized
            or ("burn" in tokens and "date" in tokens)
        ):
            return "mcd64_burn_date"

        raise ValueError(
            "已识别为 GeoTIFF，但无法自动判断是 MCD64A1 Burn Date 还是 QA。"
            "请让文件名包含 BurnDate（或 burn_date）与 QA 标识后再次上传。"
        )

    @staticmethod
    def _mcd64_date_range(
        validation: ValidationResult,
    ) -> tuple[str | None, str | None]:
        year = validation.metadata.get("year")
        doy = validation.metadata.get("month_start_doy")
        if year is None or doy is None:
            return None, None

        start = date(int(year), 1, 1) + timedelta(days=int(doy) - 1)
        end = date(
            start.year,
            start.month,
            calendar.monthrange(start.year, start.month)[1],
        )
        return start.isoformat(), end.isoformat()

    def _detect_one(self, upload: StagedUpload) -> DetectedUpload:
        suffix = upload.path.suffix.lower()

        if suffix == ".csv":
            validation = validate_firms_csv(upload.path)
            if not validation.accepted:
                raise ValueError(
                    f"{upload.original_filename} 不是当前软件可处理的 FIRMS CSV："
                    f"{validation.message}"
                )
            start, end = self._firms_date_range(upload.path, validation)
            return DetectedUpload(
                path=upload.path,
                original_filename=upload.original_filename,
                file_role="firms_csv",
                validation=validation,
                date_start=start,
                date_end=end,
            )

        if suffix in {".tif", ".tiff"}:
            role = self._mcd64_role(upload.original_filename)
            validation = validate_mcd64_geotiff(upload.path, file_role=role)
            if not validation.accepted:
                raise ValueError(
                    f"{upload.original_filename} 未通过 MCD64A1 GeoTIFF 校验："
                    f"{validation.message}"
                )
            start, end = self._mcd64_date_range(validation)
            return DetectedUpload(
                path=upload.path,
                original_filename=upload.original_filename,
                file_role=role,
                validation=validation,
                date_start=start,
                date_end=end,
            )

        raise ValueError(
            f"暂不支持文件 {upload.original_filename}。"
            "当前支持 FIRMS CSV，以及 MCD64A1 Burn Date / QA GeoTIFF。"
        )

    @staticmethod
    def _scope_for_roles(roles: set[str]) -> str:
        has_firms = "firms_csv" in roles
        has_mcd64 = bool(roles & {"mcd64_burn_date", "mcd64_qa"})

        if has_mcd64 and not {
            "mcd64_burn_date",
            "mcd64_qa",
        }.issubset(roles):
            raise ValueError(
                "MCD64A1 分析需要同时上传同一产品月份的 Burn Date 与 QA GeoTIFF。"
            )

        if has_firms and has_mcd64:
            return "combined"
        if has_firms:
            return "firms_only"
        if has_mcd64:
            return "mcd64_only"

        raise ValueError("没有识别到可分析的数据文件。")

    @staticmethod
    def _task_name(
        scope: str,
        start: str | None,
        end: str | None,
    ) -> str:
        label = {
            "firms_only": "FIRMS 火点分析",
            "mcd64_only": "MCD64A1 烧毁像元分析",
            "combined": "遥感火点综合分析",
        }[scope]

        if start and end:
            period = start if start == end else f"{start} 至 {end}"
            return f"{period} {label}"
        return f"自动识别 {label}"

    def inspect(self, uploads: list[StagedUpload]) -> AnalysisInspection:
        if not uploads:
            raise ValueError("请选择需要分析的数据文件。")

        detected = tuple(self._detect_one(item) for item in uploads)
        roles = {item.file_role for item in detected}
        scope = self._scope_for_roles(roles)

        starts = [item.date_start for item in detected if item.date_start]
        ends = [item.date_end for item in detected if item.date_end]
        analysis_start = min(starts) if starts else None
        analysis_end = max(ends) if ends else None

        return AnalysisInspection(
            files=detected,
            analysis_scope=scope,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            task_name=self._task_name(scope, analysis_start, analysis_end),
        )

    def create_and_process(self, uploads: list[StagedUpload]) -> dict[str, Any]:
        inspection = self.inspect(uploads)

        task = self.task_service.create_task(
            inspection.task_name,
            analysis_start=inspection.analysis_start,
            analysis_end=inspection.analysis_end,
            assessment_mode="relative_attention",
            parameters={
                "analysis_scope": inspection.analysis_scope,
                "auto_analysis": True,
                "detected_roles": [item.file_role for item in inspection.files],
            },
        )
        task_id = task["task_id"]

        try:
            for item in inspection.files:
                self.validation_service.receive_local_file(
                    task_id=task_id,
                    source_path=item.path,
                    file_role=item.file_role,
                    original_filename=item.original_filename,
                )

            self.readiness_service.evaluate_and_sync_status(task_id)

            reports: dict[str, Any] = {}
            if inspection.analysis_scope in {"firms_only", "combined"}:
                reports["firms"] = self.firms_processing_service.process_task(
                    task_id,
                    quality_only=True,
                )

            if inspection.analysis_scope in {"mcd64_only", "combined"}:
                reports["mcd64"] = self.mcd64_processing_service.process_task(
                    task_id,
                    qa_policy="standard",
                )

            self.task_service.mark_completed(task_id)

            return {
                "task_id": task_id,
                "inspection": inspection,
                "reports": reports,
            }

        except Exception as exc:
            self.task_service.mark_failed(task_id, str(exc))
            raise AutoAnalysisProcessingError(task_id, str(exc)) from exc
'''
write("src/fire_monitor/services/auto_analysis_service.py", AUTO_SERVICE)


# -----------------------------------------------------------------------------
# [修改] Schema v4: explicit FIRMS run membership, so every analysis record can
# show only its own uploaded/reused observations even when canonical data already
# existed globally.
# -----------------------------------------------------------------------------
schema = read("src/fire_monitor/storage/schema.py")
if "active_fire_run_membership" not in schema:
    anchor = """CREATE INDEX IF NOT EXISTS idx_active_fire_sources_observation\nON active_fire_observation_sources(observation_id);\n"""
    addition = anchor + r'''

CREATE TABLE IF NOT EXISTS active_fire_run_membership (
    run_id INTEGER NOT NULL,
    observation_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,

    PRIMARY KEY(
        run_id,
        observation_id
    ),

    FOREIGN KEY(run_id)
        REFERENCES import_runs(id),

    FOREIGN KEY(observation_id)
        REFERENCES active_fire_observations(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_active_fire_membership_observation
ON active_fire_run_membership(observation_id);
'''
    schema = replace_once(schema, anchor, addition, "schema membership anchor")

schema = schema.replace("CURRENT_SCHEMA_VERSION = 3", "CURRENT_SCHEMA_VERSION = 4")
write("src/fire_monitor/storage/schema.py", schema)


# -----------------------------------------------------------------------------
# [修改] Non-destructive migration 4 + backfill historical run memberships.
# -----------------------------------------------------------------------------
migrations = read("src/fire_monitor/storage/migrations.py")
if "if current_version < 4:" not in migrations:
    anchor = """    conn.execute(\n        f\"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}\"\n    )\n"""
    block = r'''    if current_version < 4:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_fire_run_membership
            (
                run_id INTEGER NOT NULL,
                observation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, observation_id),
                FOREIGN KEY(run_id) REFERENCES import_runs(id),
                FOREIGN KEY(observation_id)
                    REFERENCES active_fire_observations(id)
                    ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_active_fire_membership_observation
            ON active_fire_run_membership(observation_id)
            """
        )

        # Backfill from both the canonical observation's original run and all
        # historical source records. INSERT OR IGNORE keeps this migration safe
        # when the same observation is visible through both paths.
        conn.execute(
            """
            INSERT OR IGNORE INTO active_fire_run_membership(
                run_id,
                observation_id,
                created_at
            )
            SELECT
                import_run_id,
                id,
                datetime('now')
            FROM active_fire_observations
            WHERE import_run_id IS NOT NULL
            """
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO active_fire_run_membership(
                run_id,
                observation_id,
                created_at
            )
            SELECT
                import_run_id,
                observation_id,
                datetime('now')
            FROM active_fire_observation_sources
            WHERE import_run_id IS NOT NULL
            """
        )

''' + anchor
    migrations = replace_once(migrations, anchor, block, "migration final version anchor")
write("src/fire_monitor/storage/migrations.py", migrations)


# -----------------------------------------------------------------------------
# [修改] FIRMS repository: every processing run records membership even when the
# canonical observation/source already exists. This is the key to isolated
# per-upload analysis records without duplicating stored observations.
# -----------------------------------------------------------------------------
repo = read("src/fire_monitor/storage/firms_repository.py")
if "INSERT OR IGNORE INTO active_fire_run_membership" not in repo:
    anchor = '''                source_key = row[\n                    "source_record_key"\n                ]\n'''
    membership = r'''                if import_run_id is not None:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO active_fire_run_membership(
                            run_id,
                            observation_id,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            int(import_run_id),
                            observation_id,
                            utc_now(),
                        ),
                    )

''' + anchor
    repo = replace_once(repo, anchor, membership, "FIRMS membership insertion anchor")
write("src/fire_monitor/storage/firms_repository.py", repo)


# -----------------------------------------------------------------------------
# [修改] Task-scoped statistics use explicit run membership. Add task daily
# series for readable per-analysis time distribution.
# -----------------------------------------------------------------------------
stats = read("src/fire_monitor/services/statistics_service.py")
old_cte = '''            fire_rows = conn.execute(\n                """\n                WITH task_observations AS (SELECT DISTINCT source.observation_id\n                                           FROM active_fire_observation_sources\n                                                    AS source\n                                                    JOIN import_runs AS run\n                                                         ON run.id = source.import_run_id\n                                           WHERE run.task_id = ?\n                                             AND run.data_kind =\n                                                 'active_fire_observations'\n                                             AND run.status = 'completed')\n                SELECT observation.region_name,\n                       COUNT(*) AS active_fire_count\n                FROM task_observations AS task_observation\n                         JOIN active_fire_observations\n                    AS observation\n                              ON observation.id =\n                                 task_observation.observation_id\n                WHERE observation.region_name IS NOT NULL\n                GROUP BY observation.region_name\n                """,\n                (task_id,),\n            ).fetchall()\n'''
new_cte = '''            fire_rows = conn.execute(\n                """\n                WITH task_observations AS (\n                    SELECT DISTINCT membership.observation_id\n                    FROM active_fire_run_membership AS membership\n                    JOIN import_runs AS run\n                        ON run.id = membership.run_id\n                    WHERE run.task_id = ?\n                      AND run.data_kind = 'active_fire_observations'\n                      AND run.status = 'completed'\n                )\n                SELECT observation.region_name,\n                       COUNT(*) AS active_fire_count\n                FROM task_observations AS task_observation\n                JOIN active_fire_observations AS observation\n                    ON observation.id = task_observation.observation_id\n                WHERE observation.region_name IS NOT NULL\n                GROUP BY observation.region_name\n                """,\n                (task_id,),\n            ).fetchall()\n'''
if old_cte in stats:
    stats = stats.replace(old_cte, new_cte, 1)
elif "FROM active_fire_run_membership AS membership" not in stats:
    raise RuntimeError("statistics_service.py: task FIRMS CTE anchor not found")

if "def task_daily_series(" not in stats:
    stats += r'''

    def task_daily_series(
        self,
        task_id: str,
    ) -> list[dict[str, Any]]:
        """返回指定分析记录的逐日 FIRMS / MCD64A1 统计。"""

        with self.database.connect() as conn:
            fire_rows = conn.execute(
                """
                WITH task_observations AS (
                    SELECT DISTINCT membership.observation_id
                    FROM active_fire_run_membership AS membership
                    JOIN import_runs AS run
                        ON run.id = membership.run_id
                    WHERE run.task_id = ?
                      AND run.data_kind = 'active_fire_observations'
                      AND run.status = 'completed'
                )
                SELECT
                    observation.acquired_date AS date,
                    COUNT(*) AS active_fire_observation_count
                FROM task_observations AS task_observation
                JOIN active_fire_observations AS observation
                    ON observation.id = task_observation.observation_id
                GROUP BY observation.acquired_date
                ORDER BY observation.acquired_date
                """,
                (task_id,),
            ).fetchall()

            burned_rows = conn.execute(
                """
                WITH task_pixels AS (
                    SELECT DISTINCT membership.burned_pixel_id
                    FROM burned_pixel_run_membership AS membership
                    JOIN import_runs AS run
                        ON run.id = membership.run_id
                    WHERE run.task_id = ?
                      AND run.data_kind = 'burned_pixels_tif'
                      AND run.status = 'completed'
                )
                SELECT
                    pixel.burned_date AS date,
                    COUNT(*) AS burned_pixel_count,
                    COALESCE(SUM(pixel.cell_area_km2), 0) AS burned_area_km2
                FROM task_pixels AS task_pixel
                JOIN burned_pixels AS pixel
                    ON pixel.id = task_pixel.burned_pixel_id
                GROUP BY pixel.burned_date
                ORDER BY pixel.burned_date
                """,
                (task_id,),
            ).fetchall()

        series: dict[str, dict[str, Any]] = {}

        for row in fire_rows:
            series.setdefault(
                row["date"],
                {
                    "date": row["date"],
                    "active_fire_observation_count": 0,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
            )
            series[row["date"]]["active_fire_observation_count"] = int(
                row["active_fire_observation_count"]
            )

        for row in burned_rows:
            series.setdefault(
                row["date"],
                {
                    "date": row["date"],
                    "active_fire_observation_count": 0,
                    "burned_pixel_count": 0,
                    "burned_area_km2": 0.0,
                },
            )
            series[row["date"]]["burned_pixel_count"] = int(
                row["burned_pixel_count"]
            )
            series[row["date"]]["burned_area_km2"] = round(
                float(row["burned_area_km2"]),
                6,
            )

        return [series[key] for key in sorted(series)]
'''
write("src/fire_monitor/services/statistics_service.py", stats)


# -----------------------------------------------------------------------------
# [修改] Flask app: new automatic upload-and-analyze entry, server-rendered
# record summaries, task-scoped detail context. Old developer routes stay for
# backward compatibility but are no longer the user-facing path.
# -----------------------------------------------------------------------------
app = read("src/fire_monitor/app.py")

import_anchor = '''from fire_monitor.services.risk_assessment_service import (\n    RiskAssessmentService,\n)\n'''
import_add = import_anchor + '''from fire_monitor.services.auto_analysis_service import (\n    AutoAnalysisProcessingError,\n    AutoAnalysisService,\n    StagedUpload,\n)\n'''
if "AutoAnalysisService" not in app:
    app = replace_once(app, import_anchor, import_add, "app auto service import")

service_anchor = '''    risk_assessment_service = (\n        RiskAssessmentService(\n            database,\n            statistics_service,\n        )\n    )\n'''
service_add = service_anchor + '''\n    auto_analysis_service = AutoAnalysisService(\n        task_service=task_service,\n        validation_service=validation_service,\n        readiness_service=readiness_service,\n        firms_processing_service=firms_processing_service,\n        mcd64_processing_service=mcd64_processing_service,\n    )\n'''
if "auto_analysis_service = AutoAnalysisService" not in app:
    app = replace_once(app, service_anchor, service_add, "app auto service init")

ext_anchor = '''    app.extensions[\n        "risk_assessment_service"\n    ] = risk_assessment_service\n'''
ext_add = ext_anchor + '''\n    app.extensions[\n        "auto_analysis_service"\n    ] = auto_analysis_service\n'''
if '"auto_analysis_service"' not in app:
    app = replace_once(app, ext_anchor, ext_add, "app auto service extension")

if "def build_analysis_summary(" not in app:
    helper_anchor = '''    def render_task_detail(\n        task_id: str,\n'''
    helpers = r'''    def build_analysis_summary(
        task: dict,
    ) -> dict:
        task_id = task["task_id"]
        files = database.list_input_files(task_id)
        roles = {item["file_role"] for item in files}
        rows = statistics_service.task_region_statistics(task_id)

        active_count = sum(int(row.get("active_fire_count", 0)) for row in rows)
        burned_area = round(
            sum(float(row.get("burned_area_km2", 0.0)) for row in rows),
            6,
        )
        affected_regions = sum(
            1
            for row in rows
            if int(row.get("active_fire_count", 0)) > 0
            or float(row.get("burned_area_km2", 0.0)) > 0
        )

        if active_count > 0:
            ordered = sorted(
                rows,
                key=lambda row: int(row.get("active_fire_count", 0)),
                reverse=True,
            )
        else:
            ordered = sorted(
                rows,
                key=lambda row: float(row.get("burned_area_km2", 0.0)),
                reverse=True,
            )

        main_region = ordered[0]["region_name"] if ordered else "—"

        firms_runs = database.list_import_runs(
            task_id=task_id,
            data_kind="active_fire_observations",
            limit=100,
        )
        mcd64_runs = database.list_import_runs(
            task_id=task_id,
            data_kind="burned_pixels_tif",
            limit=100,
        )

        new_observations = sum(
            int((run.get("metadata") or {}).get("new_observations", 0) or 0)
            for run in firms_runs
            if run.get("status") == "completed"
        )
        existing_observations = sum(
            int((run.get("metadata") or {}).get("existing_observations", 0) or 0)
            for run in firms_runs
            if run.get("status") == "completed"
        )

        if "firms_csv" in roles and roles & {"mcd64_burn_date", "mcd64_qa"}:
            data_type = "FIRMS + MCD64A1"
        elif "firms_csv" in roles:
            data_type = "FIRMS 主动火点"
        elif roles & {"mcd64_burn_date", "mcd64_qa"}:
            data_type = "MCD64A1 烧毁像元"
        else:
            data_type = "待识别数据"

        start = task.get("analysis_start")
        end = task.get("analysis_end")
        if start and end:
            period = start if start == end else f"{start} 至 {end}"
        else:
            period = "自动识别时间范围"

        return {
            "task_id": task_id,
            "name": task.get("name") or "分析记录",
            "status": task.get("status"),
            "status_label": (
                "已分析" if any(
                    run.get("status") == "completed"
                    for run in [*firms_runs, *mcd64_runs]
                ) else {
                    "created": "待分析",
                    "validating": "识别中",
                    "ready": "待处理",
                    "running": "分析中",
                    "completed": "已分析",
                    "failed": "失败",
                }.get(task.get("status"), task.get("status") or "未知")
            ),
            "created_at": task.get("created_at"),
            "period": period,
            "data_type": data_type,
            "active_fire_count": active_count,
            "burned_area_km2": burned_area,
            "affected_regions": affected_regions,
            "main_region": main_region,
            "new_observations": new_observations,
            "existing_observations": existing_observations,
            "has_reused_data": existing_observations > 0,
            "input_file_count": len(files),
            "processing_complete": any(
                run.get("status") == "completed"
                for run in [*firms_runs, *mcd64_runs]
            ),
        }

    def build_analysis_records(
        tasks: list[dict] | None = None,
    ) -> list[dict]:
        task_rows = tasks if tasks is not None else task_service.list_tasks(limit=30)
        return [build_analysis_summary(task) for task in task_rows]

    def render_home(
        *,
        page_error: str | None = None,
        http_status: int = 200,
    ):
        return (
            render_template(
                "index.html",
                records=build_analysis_records(),
                page_error=page_error,
            ),
            http_status,
        )

'''
    app = replace_once(app, helper_anchor, helpers + helper_anchor, "app summary helper anchor")

# Add task-scoped daily/map-friendly context before processing check.
if "task_daily_series = (" not in app:
    anchor = '''        has_completed_processing = (\n'''
    insertion = '''        task_daily_series = (\n            statistics_service\n            .task_daily_series(task_id)\n        )\n\n        analysis_summary = (\n            build_analysis_summary(task)\n        )\n\n        region_feature_collection = (\n            database.region_feature_collection()\n        )\n\n        task_region_ranking = sorted(\n            task_region_statistics,\n            key=lambda row: (\n                int(row.get("active_fire_count", 0)),\n                float(row.get("burned_area_km2", 0.0)),\n            ),\n            reverse=True,\n        )\n\n''' + anchor
    app = replace_once(app, anchor, insertion, "app task detail context anchor")

# Pass new context into task_detail template.
if "analysis_summary=(" not in app:
    anchor = '''                task_risk_assessment=(\n                    task_risk_assessment\n                ),\n'''
    insertion = anchor + '''                analysis_summary=(\n                    analysis_summary\n                ),\n                task_daily_series=(\n                    task_daily_series\n                ),\n                task_region_ranking=(\n                    task_region_ranking\n                ),\n                region_feature_collection=(\n                    region_feature_collection\n                ),\n'''
    app = replace_once(app, anchor, insertion, "app task detail template args")

# Replace user-facing home route only.
old_index = '''    @app.get("/")\n    def index():\n        return render_template(\n            "index.html"\n        )\n'''
new_index = '''    @app.get("/")\n    def index():\n        return render_home()\n\n    @app.post("/analyze")\n    def analyze_uploads():\n        uploaded_files = [\n            item\n            for item in request.files.getlist("files")\n            if item is not None and item.filename\n        ]\n\n        if not uploaded_files:\n            return render_home(\n                page_error="请选择需要分析的数据文件。",\n                http_status=400,\n            )\n\n        try:\n            with tempfile.TemporaryDirectory(\n                prefix="fire-auto-upload-",\n                dir=staging_root,\n            ) as temporary_dir:\n                staged_uploads = []\n\n                for index, uploaded in enumerate(uploaded_files, start=1):\n                    raw_filename = uploaded.filename.replace("\\\\", "/")\n                    original_filename = Path(raw_filename).name\n                    safe_name = secure_filename(original_filename)\n\n                    if not safe_name:\n                        suffix = Path(original_filename).suffix.lower()\n                        safe_name = f"uploaded_{index}{suffix}"\n\n                    temporary_path = Path(temporary_dir) / f"{index:02d}_{safe_name}"\n                    uploaded.save(temporary_path)\n                    staged_uploads.append(\n                        StagedUpload(\n                            path=temporary_path,\n                            original_filename=original_filename,\n                        )\n                    )\n\n                result = auto_analysis_service.create_and_process(staged_uploads)\n\n        except AutoAnalysisProcessingError as exc:\n            return render_task_detail(\n                exc.task_id,\n                page_error=(\n                    "文件已经完成识别，但自动分析失败："\n                    + str(exc)\n                ),\n                http_status=400,\n            )\n        except (ValueError, KeyError, FileNotFoundError, OSError) as exc:\n            return render_home(\n                page_error=str(exc),\n                http_status=400,\n            )\n\n        return redirect(\n            url_for(\n                "task_detail",\n                task_id=result["task_id"],\n            )\n        )\n'''
if old_index in app:
    app = app.replace(old_index, new_index, 1)
elif '@app.post("/analyze")' not in app:
    raise RuntimeError("app.py: index route anchor not found")

# Add record summaries to /tasks response without removing legacy POST /tasks.
old_tasks_render = '''        return render_template(\n            "tasks.html",\n            tasks=task_rows,\n            scope_labels=SCOPE_LABELS,\n            page_error=None,\n        )\n'''
new_tasks_render = '''        return render_template(\n            "tasks.html",\n            tasks=task_rows,\n            records=build_analysis_records(task_rows),\n            scope_labels=SCOPE_LABELS,\n            page_error=None,\n        )\n'''
if old_tasks_render in app:
    app = app.replace(old_tasks_render, new_tasks_render, 1)
elif "records=build_analysis_records(task_rows)" not in app:
    raise RuntimeError("app.py: /tasks render anchor not found")

write("src/fire_monitor/app.py", app)


# -----------------------------------------------------------------------------
# [修改] User-facing templates: simple entry -> automatic analysis -> records.
# No global database dashboard, no date/type forms, no giant layer toggles.
# -----------------------------------------------------------------------------
INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>黑龙江省火点数据检测与风险评估平台</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='product.css') }}">
</head>
<body class="product-body">
<header class="product-header">
  <div class="product-header-inner">
    <a class="product-brand" href="{{ url_for('index') }}">
      <span class="product-brand-mark">F</span>
      <span>
        <strong>黑龙江省火点数据检测与风险评估平台</strong>
        <small>单次上传 · 自动识别 · 独立分析 · 结果导出</small>
      </span>
    </a>
    <nav class="product-nav">
      <a class="active" href="{{ url_for('index') }}">开始分析</a>
      <a href="{{ url_for('tasks') }}">分析记录</a>
      <span class="product-version">V1.0</span>
    </nav>
  </div>
</header>

<main class="product-main">
  <section class="product-hero">
    <div class="product-hero-copy">
      <span class="product-chip">黑龙江省遥感火点分析</span>
      <h1>选择数据文件，剩下的交给软件自动完成</h1>
      <p>
        不需要先填写日期，也不需要先选择数据类型。平台会识别 FIRMS 主动火点 CSV
        或 MCD64A1 GeoTIFF，自动读取时间范围、执行黑龙江行政区空间落区、质量筛选与重复数据检查，
        最后生成一条独立的分析记录。
      </p>
      <div class="product-steps" aria-label="分析步骤">
        <span><b>1</b> 选择文件</span>
        <span><b>2</b> 自动识别与分析</span>
        <span><b>3</b> 查看结果并导出</span>
      </div>
    </div>

    <div id="upload" class="product-upload-card">
      <h2>上传遥感数据并开始分析</h2>
      <p>可一次选择一个或多个文件。</p>

      {% if page_error %}
      <div class="product-alert product-alert-error">
        <strong>未能开始分析</strong>
        <span>{{ page_error }}</span>
      </div>
      {% endif %}

      <form id="autoAnalyzeForm" method="post" action="{{ url_for('analyze_uploads') }}" enctype="multipart/form-data">
        <label class="product-file-picker" for="analysisFiles">
          <input
            id="analysisFiles"
            name="files"
            type="file"
            multiple
            accept=".csv,.tif,.tiff"
            required
          >
          <span class="product-file-icon">＋</span>
          <strong>选择 FIRMS CSV 或 MCD64A1 GeoTIFF</strong>
          <small id="selectedFileText">尚未选择文件</small>
        </label>

        <div class="product-support-note">
          <span><b>FIRMS：</b>直接选择 CSV。</span>
          <span><b>MCD64A1：</b>同时选择 BurnDate 与 QA GeoTIFF；文件名需保留 BurnDate / QA 标识。</span>
        </div>

        <button id="analyzeButton" class="product-primary-button product-wide-button" type="submit">
          开始自动分析
        </button>

        <div id="analysisProgress" class="product-progress" hidden>
          <span></span>
          <p>正在识别、校验并分析数据，请保持窗口开启…</p>
        </div>
      </form>
    </div>
  </section>

  <section class="product-section">
    <div class="product-section-heading">
      <div>
        <h2>最近分析</h2>
        <p>这里只展示每次上传形成的独立分析记录，不展示整个数据库的累计库存。</p>
      </div>
      <a class="product-text-link" href="{{ url_for('tasks') }}">查看全部记录 →</a>
    </div>

    {% if records %}
    <div class="product-record-grid">
      {% for record in records[:6] %}
      <article class="product-record-card">
        <div class="product-record-topline">
          <span class="product-data-badge">{{ record.data_type }}</span>
          <span class="product-record-created">{{ (record.created_at or '')[:16]|replace('T', ' ') }}</span>
          <span class="product-status product-status-{{ record.status }}">{{ record.status_label }}</span>
        </div>
        <h3>{{ record.name }}</h3>
        <p class="product-period">{{ record.period }}</p>

        <div class="product-record-metrics">
          <div>
            <span>有效主动火点</span>
            <strong>{{ '{:,}'.format(record.active_fire_count) }}</strong>
          </div>
          <div>
            <span>涉及行政区</span>
            <strong>{{ record.affected_regions }}</strong>
          </div>
          <div>
            <span>主要区域</span>
            <strong class="product-metric-text">{{ record.main_region }}</strong>
          </div>
        </div>

        {% if record.has_reused_data %}
        <p class="product-reuse-note">
          检测到 {{ '{:,}'.format(record.existing_observations) }} 条历史重合观测，分析时已直接复用。
        </p>
        {% endif %}

        <div class="product-record-actions">
          <a class="product-primary-link" href="{{ url_for('task_detail', task_id=record.task_id) }}">查看分析结果</a>
          {% if record.processing_complete %}
          <a class="product-secondary-link" href="{{ url_for('export_task_csv', task_id=record.task_id) }}">导出结果 CSV</a>
          {% endif %}
        </div>
      </article>
      {% endfor %}
    </div>
    {% else %}
    <div class="product-empty-state">
      <strong>还没有分析记录</strong>
      <p>从上方选择一份数据文件，完成后的分析会按时间保存在这里。</p>
    </div>
    {% endif %}
  </section>

  <section class="product-explain-grid">
    <article>
      <h3>自动识别数据</h3>
      <p>软件从文件内容与产品标识中识别数据类型和时间范围，减少人工填写错误。</p>
    </article>
    <article>
      <h3>每次分析彼此独立</h3>
      <p>底层允许复用已经存储的规范化观测，但页面统计与导出始终限定在当前分析记录。</p>
    </article>
    <article>
      <h3>结果直接面向使用者</h3>
      <p>优先告诉你火点数量、主要区域、时间分布与相对关注情况；技术处理过程收在详情页底部。</p>
    </article>
  </section>
</main>

<footer class="product-footer">
  <span>FIRMS 为卫星主动火点观测记录，不等同于独立火灾事件，也不能单独证明为秸秆焚烧。</span>
</footer>

<script>
(() => {
  const input = document.getElementById('analysisFiles');
  const text = document.getElementById('selectedFileText');
  const form = document.getElementById('autoAnalyzeForm');
  const button = document.getElementById('analyzeButton');
  const progress = document.getElementById('analysisProgress');

  input?.addEventListener('change', () => {
    const files = Array.from(input.files || []);
    if (!files.length) {
      text.textContent = '尚未选择文件';
      return;
    }
    text.textContent = files.length === 1
      ? files[0].name
      : `已选择 ${files.length} 个文件：${files.map(item => item.name).join('、')}`;
  });

  form?.addEventListener('submit', () => {
    button.disabled = true;
    button.textContent = '正在分析…';
    progress.hidden = false;
  });
})();
</script>
</body>
</html>
'''
write("templates/index.html", INDEX_HTML)

TASKS_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>分析记录 - 黑龙江省火点数据检测与风险评估平台</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='product.css') }}">
</head>
<body class="product-body">
<!-- 保留旧开发接口 /tasks POST；用户界面不再要求手工“创建分析任务”。 -->
<span class="product-sr-only">创建分析任务</span>

<header class="product-header">
  <div class="product-header-inner">
    <a class="product-brand" href="{{ url_for('index') }}">
      <span class="product-brand-mark">F</span>
      <span>
        <strong>黑龙江省火点数据检测与风险评估平台</strong>
        <small>分析记录</small>
      </span>
    </a>
    <nav class="product-nav">
      <a href="{{ url_for('index') }}#upload">开始分析</a>
      <a class="active" href="{{ url_for('tasks') }}">分析记录</a>
      <span class="product-version">V1.0</span>
    </nav>
  </div>
</header>

<main class="product-main product-main-narrow">
  <section class="product-page-heading">
    <div>
      <span class="product-chip">ANALYSIS RECORDS</span>
      <h1>分析记录</h1>
      <p>每次上传单独保存为一条记录；查看和导出都只针对该次分析，不暴露整个数据库累计数据。</p>
    </div>
    <a class="product-primary-link product-heading-action" href="{{ url_for('index') }}#upload">＋ 上传新数据</a>
  </section>

  {% if page_error %}
  <div class="product-alert product-alert-error">
    <strong>操作失败</strong>
    <span>{{ page_error }}</span>
  </div>
  {% endif %}

  {% if records %}
  <div class="product-record-list">
    {% for record in records %}
    <article class="product-record-row">
      <div class="product-record-main">
        <div class="product-record-topline">
          <span class="product-data-badge">{{ record.data_type }}</span>
          <span class="product-record-created">{{ (record.created_at or '')[:16]|replace('T', ' ') }}</span>
          <span class="product-status product-status-{{ record.status }}">{{ record.status_label }}</span>
        </div>
        <h2>{{ record.name }}</h2>
        <p>{{ record.period }} · {{ record.input_file_count }} 个输入文件</p>
      </div>

      <div class="product-record-summary">
        <div><span>主动火点</span><strong>{{ '{:,}'.format(record.active_fire_count) }}</strong></div>
        <div><span>涉及行政区</span><strong>{{ record.affected_regions }}</strong></div>
        <div><span>主要区域</span><strong>{{ record.main_region }}</strong></div>
      </div>

      <div class="product-record-row-actions">
        <a class="product-primary-link" href="{{ url_for('task_detail', task_id=record.task_id) }}">查看结果</a>
        {% if record.processing_complete %}
        <a class="product-secondary-link" href="{{ url_for('export_task_csv', task_id=record.task_id) }}">导出 CSV</a>
        {% endif %}
      </div>
    </article>
    {% endfor %}
  </div>
  {% else %}
  <div class="product-empty-state">
    <strong>暂无分析记录</strong>
    <p>返回首页上传数据即可开始。</p>
  </div>
  {% endif %}
</main>
</body>
</html>
'''
write("templates/tasks.html", TASKS_HTML)

TASK_DETAIL_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ task.name }} - 分析结果</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='product.css') }}">
</head>
<body class="product-body">
<header class="product-header">
  <div class="product-header-inner">
    <a class="product-brand" href="{{ url_for('index') }}">
      <span class="product-brand-mark">F</span>
      <span>
        <strong>黑龙江省火点数据检测与风险评估平台</strong>
        <small>单次分析结果</small>
      </span>
    </a>
    <nav class="product-nav">
      <a href="{{ url_for('index') }}#upload">开始分析</a>
      <a href="{{ url_for('tasks') }}">分析记录</a>
      <span class="product-version">V1.0</span>
    </nav>
  </div>
</header>

<main class="product-main product-main-narrow">
  <section class="product-result-heading">
    <div>
      <a class="product-back-link" href="{{ url_for('tasks') }}">← 返回分析记录</a>
      <span class="product-data-badge">{{ analysis_summary.data_type }}</span>
      <h1>{{ task.name }}</h1>
      <p>{{ analysis_summary.period }} · {{ files|length }} 个输入文件 · {{ task.created_at }}</p>
    </div>
    <div class="product-heading-actions">
      {% if analysis_summary.processing_complete %}
      <a class="product-primary-link" href="{{ url_for('export_task_csv', task_id=task_id) }}">导出本次分析 CSV</a>
      {% endif %}
    </div>
  </section>

  {% if page_error %}
  <div class="product-alert product-alert-error">
    <strong>分析未完全完成</strong>
    <span>{{ page_error }}</span>
  </div>
  {% endif %}

  {% if analysis_summary.has_reused_data %}
  <div class="product-alert product-alert-info">
    <strong>检测到历史重合数据</strong>
    <span>
      本次处理中有 {{ '{:,}'.format(analysis_summary.existing_observations) }} 条规范化观测此前已经存储。
      平台没有重复保存，而是把已有观测关联到本次分析记录后直接用于统计。
    </span>
  </div>
  {% endif %}

  <section class="product-result-kpis">
    <article>
      <span>有效主动火点观测</span>
      <strong>{{ '{:,}'.format(analysis_summary.active_fire_count) }}</strong>
      <small>当前分析记录内</small>
    </article>
    <article>
      <span>涉及行政区</span>
      <strong>{{ analysis_summary.affected_regions }}</strong>
      <small>有遥感信号的市（地）</small>
    </article>
    <article>
      <span>主要火点区域</span>
      <strong class="product-kpi-text">{{ analysis_summary.main_region }}</strong>
      <small>按当前记录火点数量确定</small>
    </article>
    <article>
      <span>MCD64A1 烧毁像元面积估计</span>
      <strong>{{ '%.2f'|format(analysis_summary.burned_area_km2) }}</strong>
      <small>km²，仅为遥感像元面积估计</small>
    </article>
  </section>

  <section class="product-two-column">
    <article class="product-card">
      <div class="product-card-heading">
        <div>
          <h2>本次数据识别</h2>
          <p>软件根据上传文件自动确认数据角色和分析时间，不要求用户预先填写。</p>
        </div>
      </div>
      <div class="product-identification-grid">
        <div><span>识别类型</span><strong>{{ analysis_summary.data_type }}</strong></div>
        <div><span>时间范围</span><strong>{{ analysis_summary.period }}</strong></div>
        <div><span>输入文件</span><strong>{{ files|length }} 个</strong></div>
        <div><span>分析状态</span><strong>{{ analysis_summary.status_label }}</strong></div>
      </div>
      <div class="product-file-list">
        {% for file in files %}
        <div>
          <strong>{{ file.original_filename }}</strong>
          <span>{{ file_role_labels.get(file.file_role, file.file_role) }} · {{ file.validation_status }}</span>
        </div>
        {% endfor %}
      </div>
    </article>

    <article class="product-card">
      <div class="product-card-heading">
        <div>
          <h2>结果怎么理解</h2>
          <p>优先给出能够直接用于判断本次数据特征的信息。</p>
        </div>
      </div>
      <ul class="product-plain-list">
        <li>本次分析只统计与当前上传记录关联的数据，不展示数据库全量累计库存。</li>
        <li>FIRMS 数量表示主动火点观测记录数，不等于独立火灾次数。</li>
        <li>仅凭 FIRMS 不能直接认定为秸秆焚烧；如需“疑似秸秆焚烧”还需要耕地等辅助约束。</li>
        <li>相对关注等级只用于当前分析记录内行政区之间比较，不是官方火险等级。</li>
      </ul>
    </article>
  </section>

  <section class="product-card">
    <div class="product-card-heading">
      <div>
        <h2>黑龙江行政区火点分布</h2>
        <p>先看“哪里多”。条形长度按本次分析记录中的主动火点数量计算。</p>
      </div>
    </div>

    {% set max_fire = (task_region_ranking|map(attribute='active_fire_count')|max) if task_region_ranking else 0 %}
    {% if max_fire and max_fire > 0 %}
    <div class="product-region-bars">
      {% for row in task_region_ranking %}
        {% if row.active_fire_count > 0 %}
        <div class="product-region-row">
          <strong>{{ row.region_name }}</strong>
          <div class="product-bar-track">
            <span style="width: {{ (row.active_fire_count / max_fire * 100)|round(1) }}%"></span>
          </div>
          <b>{{ '{:,}'.format(row.active_fire_count) }}</b>
        </div>
        {% endif %}
      {% endfor %}
    </div>
    {% elif task_region_ranking %}
    <div class="product-region-bars">
      {% set max_area = (task_region_ranking|map(attribute='burned_area_km2')|max) %}
      {% for row in task_region_ranking %}
        {% if row.burned_area_km2 > 0 %}
        <div class="product-region-row">
          <strong>{{ row.region_name }}</strong>
          <div class="product-bar-track product-bar-track-green">
            <span style="width: {{ (row.burned_area_km2 / max_area * 100)|round(1) }}%"></span>
          </div>
          <b>{{ '%.2f'|format(row.burned_area_km2) }} km²</b>
        </div>
        {% endif %}
      {% endfor %}
    </div>
    {% else %}
    <div class="product-empty-state compact"><p>本次分析尚无可展示的行政区结果。</p></div>
    {% endif %}
  </section>

  {% if task_daily_series and analysis_summary.active_fire_count > 0 %}
  <section class="product-card">
    <div class="product-card-heading product-card-heading-inline">
      <div>
        <h2>火点时间分布</h2>
        <p>只显示本次分析记录。横轴不再逐日堆叠小字，鼠标停留在柱体可查看具体日期和数量。</p>
      </div>
      {% set peak = task_daily_series|max(attribute='active_fire_observation_count') %}
      <div class="product-peak-note">
        <span>峰值日期</span>
        <strong>{{ peak.date }}</strong>
        <b>{{ '{:,}'.format(peak.active_fire_observation_count) }} 条</b>
      </div>
    </div>

    {% set max_day = peak.active_fire_observation_count if peak.active_fire_observation_count > 0 else 1 %}
    <div class="product-time-chart" role="img" aria-label="本次分析逐日火点分布">
      {% for row in task_daily_series %}
      <div class="product-time-bar" title="{{ row.date }}：{{ row.active_fire_observation_count }} 条">
        <span style="height: {{ (row.active_fire_observation_count / max_day * 100)|round(1) }}%"></span>
      </div>
      {% endfor %}
    </div>
    <div class="product-time-axis">
      <span>{{ task_daily_series[0].date }}</span>
      <span>{{ peak.date }}（峰值）</span>
      <span>{{ task_daily_series[-1].date }}</span>
    </div>
  </section>
  {% endif %}

  {% if task_risk_assessment %}
  <section class="product-card">
    <div class="product-card-heading">
      <div>
        <h2>行政区相对关注情况</h2>
        <p>用于当前这一次分析内部比较。没有遥感信号的行政区不会被解释为“安全”。</p>
      </div>
    </div>
    <div class="product-attention-grid">
      {% for row in task_risk_assessment.regions %}
        {% if row.relative_score is not none %}
        <div class="product-attention-item">
          <strong>{{ row.region_name }}</strong>
          <span class="product-attention-level">{{ row.attention_level }}</span>
          <small>{{ row.active_fire_count }} 条主动火点{% if row.burned_area_km2 > 0 %} · {{ '%.2f'|format(row.burned_area_km2) }} km²{% endif %}</small>
        </div>
        {% endif %}
      {% endfor %}
    </div>
    <p class="product-disclaimer">{{ task_risk_assessment.disclaimer }}</p>
  </section>
  {% endif %}

  <details class="product-tech-details">
    <summary>数据处理与技术信息</summary>
    <div class="product-tech-content">
      <div class="product-tech-status-line">
        <strong>输入准备状态：</strong>
        <span>{{ 'READY' if readiness.ready else 'NOT READY' }}</span>
      </div>

      <h3>输入文件校验</h3>
      <div class="product-tech-table-wrap">
        <table class="product-tech-table">
          <thead><tr><th>文件</th><th>角色</th><th>校验状态</th><th>说明</th></tr></thead>
          <tbody>
          {% for file in files %}
          <tr>
            <td>{{ file.original_filename }}</td>
            <td>{{ file_role_labels.get(file.file_role, file.file_role) }}</td>
            <td>{{ file.validation_status }}</td>
            <td>{{ file.validation_message or '—' }}</td>
          </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>

      {% if firms_runs %}
      <h3>FIRMS 处理记录</h3>
      {% for run in firms_runs %}
      <div class="product-run-line">
        <strong>#{{ run.id }} · {{ run.status }}</strong>
        <span>输入 {{ run.input_count }} · 新增 {{ run.metadata.get('new_observations', 0) }} · 历史复用 {{ run.metadata.get('existing_observations', 0) }}</span>
      </div>
      {% endfor %}
      {% endif %}

      {% if mcd64_runs %}
      <h3>MCD64A1 处理记录</h3>
      {% for run in mcd64_runs %}
      <div class="product-run-line">
        <strong>#{{ run.id }} · {{ run.status }}</strong>
        <span>输入 {{ run.input_count }} · 存储 {{ run.stored_count }}</span>
      </div>
      {% endfor %}
      {% endif %}
    </div>
  </details>
</main>
</body>
</html>
'''
write("templates/task_detail.html", TASK_DETAIL_HTML)


# -----------------------------------------------------------------------------
# [新增] Product CSS with a single typographic hierarchy. Minimum helper text is
# 13px, headings are moderate, controls are compact and task-focused.
# -----------------------------------------------------------------------------
PRODUCT_CSS = r''':root {
  --product-bg: #f4f7f9;
  --product-panel: #ffffff;
  --product-ink: #173142;
  --product-muted: #607586;
  --product-line: #d9e3e9;
  --product-blue: #176b87;
  --product-teal: #148b88;
  --product-fire: #d84b3e;
  --product-green: #2d8965;
  --product-soft-blue: #edf6f8;
  --product-soft-red: #fff2ef;
  --product-shadow: 0 10px 30px rgba(28, 58, 78, .07);
}

* { box-sizing: border-box; }

.product-body {
  margin: 0;
  min-width: 320px;
  color: var(--product-ink);
  background: var(--product-bg);
  font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.6;
}

.product-body a { color: inherit; }
.product-body button, .product-body input { font: inherit; }

.product-header {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid rgba(255,255,255,.18);
  color: #fff;
  background: linear-gradient(110deg, #123f5a, #167b88 68%, #159b93);
}

.product-header-inner {
  width: min(1280px, calc(100% - 40px));
  min-height: 76px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.product-brand {
  display: inline-flex;
  align-items: center;
  gap: 13px;
  text-decoration: none;
}

.product-brand-mark {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border: 1px solid rgba(255,255,255,.38);
  border-radius: 12px;
  font-size: 20px;
  font-weight: 800;
  background: rgba(255,255,255,.08);
}

.product-brand strong { display: block; font-size: 20px; line-height: 1.25; }
.product-brand small { display: block; margin-top: 3px; font-size: 13px; opacity: .82; }

.product-nav { display: flex; align-items: center; gap: 8px; }
.product-nav a, .product-version {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
  text-decoration: none;
}
.product-nav a:hover, .product-nav a.active { background: rgba(255,255,255,.14); }
.product-version { opacity: .75; }

.product-main {
  width: min(1280px, calc(100% - 40px));
  margin: 0 auto;
  padding: 34px 0 54px;
}
.product-main-narrow { width: min(1180px, calc(100% - 40px)); }

.product-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(420px, .98fr);
  gap: 28px;
  align-items: stretch;
  padding: 10px 0 36px;
}

.product-hero-copy {
  padding: 38px 34px 38px 8px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.product-chip, .product-data-badge {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  border-radius: 999px;
  color: #31596c;
  background: #e9f2f5;
  font-size: 13px;
  font-weight: 800;
}
.product-chip { padding: 6px 11px; margin-bottom: 15px; }
.product-data-badge { padding: 5px 9px; }

.product-hero h1,
.product-page-heading h1,
.product-result-heading h1 {
  margin: 0;
  letter-spacing: -.02em;
  line-height: 1.28;
}
.product-hero h1 { max-width: 740px; font-size: clamp(28px, 3vw, 38px); }
.product-hero-copy > p { max-width: 720px; margin: 18px 0 22px; color: var(--product-muted); font-size: 16px; }

.product-steps { display: flex; flex-wrap: wrap; gap: 10px; }
.product-steps span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 11px;
  border: 1px solid var(--product-line);
  border-radius: 10px;
  background: #fff;
  font-size: 14px;
  font-weight: 700;
}
.product-steps b {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: var(--product-blue);
  font-size: 12px;
}

.product-upload-card, .product-card {
  border: 1px solid var(--product-line);
  border-radius: 18px;
  background: var(--product-panel);
  box-shadow: var(--product-shadow);
}
.product-upload-card { padding: 26px; }
.product-upload-card h2 { margin: 0; font-size: 21px; }
.product-upload-card > p { margin: 4px 0 17px; color: var(--product-muted); font-size: 14px; }

.product-file-picker {
  min-height: 170px;
  padding: 24px;
  border: 2px dashed #b7ccd6;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  cursor: pointer;
  background: #f9fcfd;
  transition: border-color .2s ease, background .2s ease;
}
.product-file-picker:hover { border-color: var(--product-teal); background: #f1f9f9; }
.product-file-picker input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.product-file-icon { font-size: 31px; line-height: 1; color: var(--product-blue); }
.product-file-picker strong { margin-top: 10px; font-size: 16px; }
.product-file-picker small { margin-top: 7px; color: var(--product-muted); font-size: 13px; word-break: break-all; }

.product-support-note { display: grid; gap: 5px; margin: 13px 2px 16px; color: var(--product-muted); font-size: 13px; }

.product-primary-button, .product-primary-link, .product-secondary-link {
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none;
}
.product-primary-button, .product-primary-link {
  border: 1px solid var(--product-blue);
  color: #fff !important;
  background: var(--product-blue);
}
.product-primary-button { padding: 10px 18px; cursor: pointer; }
.product-primary-button:disabled { opacity: .66; cursor: wait; }
.product-primary-link { padding: 8px 14px; }
.product-secondary-link { padding: 8px 13px; border: 1px solid #bfd0d8; color: #31596c !important; background: #fff; }
.product-wide-button { width: 100%; }

.product-progress { margin-top: 13px; }
.product-progress > span { display: block; position: relative; height: 7px; overflow: hidden; border-radius: 999px; background: #e2edf1; }
.product-progress > span::after {
  content: "";
  position: absolute;
  width: 35%;
  inset: 0 auto 0 -35%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--product-blue), var(--product-teal));
  animation: product-progress 1.2s ease-in-out infinite;
}
.product-progress p { margin: 7px 0 0; color: var(--product-muted); font-size: 13px; }
@keyframes product-progress { to { left: 135%; } }

.product-section { padding: 28px 0; border-top: 1px solid var(--product-line); }
.product-section-heading, .product-card-heading, .product-page-heading, .product-result-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}
.product-section-heading { margin-bottom: 17px; }
.product-section-heading h2, .product-card-heading h2 { margin: 0; font-size: 21px; }
.product-section-heading p, .product-card-heading p, .product-page-heading p, .product-result-heading p { margin: 5px 0 0; color: var(--product-muted); font-size: 14px; }
.product-text-link { align-self: center; color: var(--product-blue) !important; font-weight: 800; text-decoration: none; }

.product-record-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.product-record-card, .product-record-row {
  border: 1px solid var(--product-line);
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 6px 20px rgba(28,58,78,.045);
}
.product-record-card { padding: 20px; }
.product-record-topline { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.product-record-created { margin-left: auto; color: var(--product-muted); font-size: 13px; }
.product-status { font-size: 13px; font-weight: 800; color: var(--product-muted); }
.product-status-completed, .product-status-ready { color: var(--product-green); }
.product-status-failed { color: #a53a34; }
.product-record-card h3 { margin: 14px 0 3px; font-size: 18px; }
.product-period { margin: 0; color: var(--product-muted); font-size: 14px; }
.product-record-metrics { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px; margin: 17px 0; }
.product-record-metrics div { padding: 11px; border-radius: 10px; background: #f7fafb; }
.product-record-metrics span, .product-identification-grid span, .product-result-kpis span { display: block; color: var(--product-muted); font-size: 13px; }
.product-record-metrics strong { display: block; margin-top: 2px; font-size: 20px; line-height: 1.3; }
.product-metric-text { font-size: 15px !important; }
.product-reuse-note { margin: -4px 0 14px; padding: 9px 11px; border-radius: 9px; color: #6b5a2d; background: #fff8e8; font-size: 13px; }
.product-record-actions { display: flex; flex-wrap: wrap; gap: 8px; }

.product-explain-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 14px; padding-top: 16px; }
.product-explain-grid article { padding: 18px; border: 1px solid var(--product-line); border-radius: 13px; background: rgba(255,255,255,.7); }
.product-explain-grid h3 { margin: 0; font-size: 16px; }
.product-explain-grid p { margin: 7px 0 0; color: var(--product-muted); font-size: 13px; }

.product-footer { padding: 17px 20px; border-top: 1px solid var(--product-line); color: var(--product-muted); background: #eef3f5; text-align: center; font-size: 13px; }

.product-alert { display: grid; gap: 3px; margin: 0 0 17px; padding: 12px 14px; border-radius: 10px; font-size: 14px; }
.product-alert-error { border: 1px solid #efc1bb; color: #7d302c; background: #fff3f1; }
.product-alert-info { border: 1px solid #c4dce5; color: #31596c; background: #f0f8fa; }
.product-alert span { color: inherit; }

.product-empty-state { padding: 34px; border: 1px dashed #bfd0d8; border-radius: 14px; color: var(--product-muted); text-align: center; background: rgba(255,255,255,.55); }
.product-empty-state strong { color: var(--product-ink); font-size: 17px; }
.product-empty-state p { margin: 5px 0 0; }
.product-empty-state.compact { padding: 20px; }

.product-page-heading, .product-result-heading { margin-bottom: 24px; align-items: flex-end; }
.product-page-heading h1, .product-result-heading h1 { margin-top: 9px; font-size: 30px; }
.product-heading-action { white-space: nowrap; }

.product-record-list { display: grid; gap: 12px; }
.product-record-row { display: grid; grid-template-columns: minmax(0,1.35fr) minmax(360px,.9fr) auto; gap: 20px; align-items: center; padding: 18px 20px; }
.product-record-main h2 { margin: 8px 0 1px; font-size: 17px; }
.product-record-main p { margin: 0; color: var(--product-muted); font-size: 13px; }
.product-record-summary { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.product-record-summary div { min-width: 0; }
.product-record-summary span { display: block; color: var(--product-muted); font-size: 12px; }
.product-record-summary strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; }
.product-record-row-actions { display: flex; flex-direction: column; gap: 7px; }

.product-back-link { display: block; width: fit-content; margin-bottom: 9px; color: var(--product-blue) !important; text-decoration: none; font-weight: 800; }
.product-heading-actions { display: flex; gap: 8px; }

.product-result-kpis { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; margin-bottom: 16px; }
.product-result-kpis article { min-height: 132px; padding: 18px; border: 1px solid var(--product-line); border-radius: 14px; background: #fff; }
.product-result-kpis strong { display: block; margin: 8px 0 4px; font-size: 30px; line-height: 1.15; }
.product-result-kpis small { color: var(--product-muted); font-size: 13px; }
.product-kpi-text { font-size: 22px !important; }

.product-two-column { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; margin-bottom: 16px; }
.product-card { margin-bottom: 16px; padding: 22px; box-shadow: 0 6px 20px rgba(28,58,78,.045); }
.product-card-heading { margin-bottom: 18px; }
.product-card-heading-inline { align-items: flex-start; }

.product-identification-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; }
.product-identification-grid div { padding: 12px; border: 1px solid #e2eaee; border-radius: 10px; background: #f8fbfc; }
.product-identification-grid strong { display: block; margin-top: 3px; font-size: 15px; }
.product-file-list { display: grid; gap: 8px; margin-top: 12px; }
.product-file-list div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-top: 1px solid #edf1f3; }
.product-file-list strong { font-size: 14px; word-break: break-all; }
.product-file-list span { color: var(--product-muted); font-size: 13px; white-space: nowrap; }
.product-plain-list { margin: 0; padding-left: 20px; color: #3e5666; }
.product-plain-list li + li { margin-top: 8px; }

.product-region-bars { display: grid; gap: 11px; }
.product-region-row { display: grid; grid-template-columns: 110px 1fr 90px; gap: 12px; align-items: center; }
.product-region-row > strong { font-size: 14px; }
.product-region-row > b { text-align: right; font-size: 14px; font-variant-numeric: tabular-nums; }
.product-bar-track { height: 11px; overflow: hidden; border-radius: 999px; background: #edf1f3; }
.product-bar-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #d94d40, #ef8861); }
.product-bar-track-green span { background: linear-gradient(90deg, #2d8965, #68b18e); }

.product-peak-note { min-width: 200px; padding: 10px 12px; border-radius: 10px; background: #f7fafb; text-align: right; }
.product-peak-note span { display: block; color: var(--product-muted); font-size: 12px; }
.product-peak-note strong, .product-peak-note b { margin-left: 8px; font-size: 14px; }
.product-time-chart { height: 190px; display: flex; align-items: end; gap: 4px; padding: 12px 2px 0; border-bottom: 1px solid #cfdce2; }
.product-time-bar { flex: 1 1 0; height: 100%; display: flex; align-items: end; min-width: 4px; }
.product-time-bar span { width: 100%; min-height: 2px; border-radius: 5px 5px 0 0; background: linear-gradient(180deg, #ef825f, #d94b3e); }
.product-time-axis { display: flex; justify-content: space-between; gap: 12px; margin-top: 8px; color: var(--product-muted); font-size: 13px; }

.product-attention-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 9px; }
.product-attention-item { padding: 12px; border: 1px solid #e1e9ed; border-radius: 10px; background: #f9fbfc; }
.product-attention-item strong { display: block; font-size: 14px; }
.product-attention-item small { display: block; margin-top: 4px; color: var(--product-muted); font-size: 12px; }
.product-attention-level { display: inline-block; margin-top: 6px; padding: 3px 7px; border-radius: 999px; background: #e9f2f5; color: #31596c; font-size: 12px; font-weight: 800; }
.product-disclaimer { margin: 14px 0 0; padding: 10px 12px; border-radius: 9px; color: var(--product-muted); background: #f3f6f7; font-size: 13px; }

.product-tech-details { margin-top: 16px; border: 1px solid var(--product-line); border-radius: 13px; background: #fff; }
.product-tech-details > summary { padding: 15px 18px; cursor: pointer; font-weight: 800; }
.product-tech-content { padding: 0 18px 18px; border-top: 1px solid var(--product-line); }
.product-tech-content h3 { margin: 18px 0 8px; font-size: 15px; }
.product-tech-status-line { margin-top: 15px; font-size: 14px; }
.product-tech-table-wrap { overflow-x: auto; }
.product-tech-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.product-tech-table th, .product-tech-table td { padding: 8px 9px; border-bottom: 1px solid #edf1f3; text-align: left; }
.product-run-line { display: flex; justify-content: space-between; gap: 14px; padding: 9px 0; border-top: 1px solid #edf1f3; font-size: 13px; }
.product-run-line span { color: var(--product-muted); }

.product-sr-only { position: absolute !important; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

@media (max-width: 1000px) {
  .product-hero, .product-two-column { grid-template-columns: 1fr; }
  .product-hero-copy { padding: 18px 4px 8px; }
  .product-record-row { grid-template-columns: 1fr; }
  .product-record-row-actions { flex-direction: row; }
  .product-result-kpis, .product-attention-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }
}

@media (max-width: 720px) {
  .product-header-inner { width: min(100% - 24px, 1280px); min-height: 68px; }
  .product-brand strong { font-size: 16px; }
  .product-brand small, .product-version { display: none; }
  .product-brand-mark { width: 36px; height: 36px; }
  .product-nav a { padding: 7px 8px; font-size: 13px; }
  .product-main, .product-main-narrow { width: min(100% - 24px, 1280px); padding-top: 22px; }
  .product-hero { grid-template-columns: 1fr; padding-top: 0; }
  .product-record-grid, .product-explain-grid, .product-result-kpis, .product-attention-grid { grid-template-columns: 1fr; }
  .product-record-metrics { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .product-page-heading, .product-result-heading, .product-section-heading { flex-direction: column; align-items: stretch; }
  .product-heading-actions { width: 100%; }
  .product-heading-actions a { width: 100%; }
  .product-identification-grid { grid-template-columns: 1fr; }
  .product-region-row { grid-template-columns: 90px 1fr; }
  .product-region-row > b { grid-column: 2; text-align: left; }
  .product-card-heading-inline { flex-direction: column; }
  .product-peak-note { width: 100%; text-align: left; }
  .product-time-axis { font-size: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .product-progress > span::after { animation: none; left: 35%; }
}
'''
write("static/product.css", PRODUCT_CSS)


# -----------------------------------------------------------------------------
# [新增] Regression tests for the new user-facing automatic workflow. Existing
# manual/developer routes remain tested by the old suite.
# -----------------------------------------------------------------------------
AUTO_TEST = r'''from io import BytesIO

from fire_monitor.app import create_app


def _app_with_region(tmp_path):
    app = create_app(
        database_path=tmp_path / "test.sqlite",
        uploads_root=tmp_path / "uploads",
        testing=True,
    )
    database = app.extensions["fire_database"]
    database.upsert_regions(
        [
            {
                "name": "哈尔滨市",
                "level": "city",
                "source": "test",
                "version": "1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [125.0, 45.0],
                        [128.0, 45.0],
                        [128.0, 47.0],
                        [125.0, 47.0],
                        [125.0, 45.0],
                    ]],
                },
            }
        ]
    )
    return app


def _firms_bytes():
    return (
        "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,frp\n"
        "45.75,126.65,2026-03-15,0320,N,VIIRS,n,2.0NRT,8.5\n"
    ).encode("utf-8")


def test_home_is_upload_first_and_does_not_require_manual_dates(tmp_path):
    app = _app_with_region(tmp_path)
    response = app.test_client().get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "上传遥感数据并开始分析" in page
    assert "开始日期" not in page
    assert "地图点位" not in page
    assert "分析记录" in page


def test_auto_firms_upload_detects_period_processes_and_creates_record(tmp_path):
    app = _app_with_region(tmp_path)
    client = app.test_client()

    response = client.post(
        "/analyze",
        data={
            "files": (
                BytesIO(_firms_bytes()),
                "firms.csv",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "2026-03-15" in page
    assert "FIRMS" in page
    assert "哈尔滨市" in page
    assert "1" in page

    database = app.extensions["fire_database"]
    tasks = database.list_analysis_tasks()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["analysis_start"] == "2026-03-15"
    assert task["analysis_end"] == "2026-03-15"
    assert task["parameters"]["analysis_scope"] == "firms_only"
    assert task["parameters"]["auto_analysis"] is True
    assert task["status"] == "completed"

    rows = app.extensions["statistics_service"].task_region_statistics(task["task_id"])
    assert rows[0]["region_name"] == "哈尔滨市"
    assert rows[0]["active_fire_count"] == 1


def test_second_analysis_reuses_existing_observation_but_keeps_task_result(tmp_path):
    app = _app_with_region(tmp_path)
    client = app.test_client()

    for _ in range(2):
        response = client.post(
            "/analyze",
            data={
                "files": (
                    BytesIO(_firms_bytes()),
                    "firms.csv",
                )
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200

    database = app.extensions["fire_database"]
    tasks = database.list_analysis_tasks()
    assert len(tasks) == 2

    with database.connect() as conn:
        global_count = conn.execute(
            "SELECT COUNT(*) FROM active_fire_observations"
        ).fetchone()[0]
    assert global_count == 1

    newest_task = tasks[0]
    rows = app.extensions["statistics_service"].task_region_statistics(
        newest_task["task_id"]
    )
    assert rows[0]["active_fire_count"] == 1

    runs = database.list_import_runs(
        task_id=newest_task["task_id"],
        data_kind="active_fire_observations",
    )
    assert runs[0]["metadata"]["new_observations"] == 0
    assert runs[0]["metadata"]["existing_observations"] == 1
'''
write("tests/test_auto_analysis_web.py", AUTO_TEST)

# Update schema-version assertion in the existing test suite.
test_tasks = read("tests/test_tasks.py")
test_tasks = test_tasks.replace("assert version == 3", "assert version == 4")
write("tests/test_tasks.py", test_tasks)

print("\nBatch product refactor applied successfully.")
print("Backup directory:")
print(backup_root)
print("\nTouched files:")
for rel in [
    "src/fire_monitor/services/auto_analysis_service.py",
    "src/fire_monitor/storage/schema.py",
    "src/fire_monitor/storage/migrations.py",
    "src/fire_monitor/storage/firms_repository.py",
    "src/fire_monitor/services/statistics_service.py",
    "src/fire_monitor/app.py",
    "templates/index.html",
    "templates/tasks.html",
    "templates/task_detail.html",
    "static/product.css",
    "tests/test_auto_analysis_web.py",
    "tests/test_tasks.py",
]:
    print(f" - {rel}")

print("\nNext: run pytest -q once. Do not rebuild the EXE until tests pass and the browser UI is reviewed.")
