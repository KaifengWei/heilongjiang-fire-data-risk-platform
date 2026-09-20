"""Flask 本地 Web 应用。"""

from __future__ import annotations

import csv
import tempfile
from io import StringIO
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from fire_monitor.config import load_settings
from fire_monitor.services.readiness_service import (
    ReadinessService,
    SUPPORTED_ANALYSIS_SCOPES,
)
from fire_monitor.services.task_service import TaskService
from fire_monitor.services.validation_service import (
    ValidationService,
)
from fire_monitor.storage.database import Database

from fire_monitor.services.firms_processing_service import (
    FirmsProcessingService,
)

from fire_monitor.services.mcd64_processing_service import (
    Mcd64ProcessingService,
)

from fire_monitor.services.statistics_service import (
    StatisticsService,
)
from fire_monitor.services.firms_intelligence_service import (
    FirmsIntelligenceService,
)
from fire_monitor.services.historical_baseline_service import (
    HistoricalFirmsBaselineService,
)
from fire_monitor.services.risk_assessment_service import (
    RiskAssessmentService,
)
from fire_monitor.services.auto_analysis_service import (
    AutoAnalysisProcessingError,
    AutoAnalysisService,
    StagedUpload,
)
from fire_monitor.services.region_service import (
    RegionService,
)
from fire_monitor.services.startup_service import (
    StartupService,
)

SCOPE_LABELS = {
    "firms_only": "仅 FIRMS 主动火点",
    "mcd64_only": "仅 MCD64A1 火烧迹地",
    "combined": "FIRMS + MCD64A1 联合分析",
}

FILE_ROLE_LABELS = {
    "firms_csv": "FIRMS 主动火点 CSV",
    "mcd64_burn_date": "MCD64A1 Burn Date GeoTIFF",
    "mcd64_qa": "MCD64A1 QA GeoTIFF",
}


def _as_optional_date(
    value: str | None,
) -> str | None:
    if not value:
        return None

    try:
        from datetime import date

        return date.fromisoformat(
            value
        ).isoformat()

    except ValueError as exc:
        raise ValueError(
            "日期应为 YYYY-MM-DD，"
            "例如 2026-03-01。"
        ) from exc


def create_app(
    database_path: str | Path | None = None,
    testing: bool = False,
    uploads_root: str | Path | None = None,
    historical_baseline_path: str | Path | None = None,
) -> Flask:
    """创建 Flask 应用。"""

    settings = load_settings(
        database_path
    )

    database = Database(
        settings.database_path
    )
    database.initialize()

    # 正式运行时，如果当前数据库还没有行政区，
    # 则从随软件发布的默认 GeoJSON 初始化黑龙江省地市边界。
    #
    # testing=True 时不自动导入，避免改变现有单元测试
    # 对“空数据库”的预期。
    if not testing:
        default_regions_path = (
                settings.project_dir
                / "data"
                / "regions"
                / "heilongjiang_city.geojson"
        )

        region_service = (
            RegionService(
                database
            )
        )

        startup_service = (
            StartupService(
                database,
                region_service,
                default_regions_path,
            )
        )

        startup_service.initialize_default_regions()

    if uploads_root is None:
        upload_root = (
            settings.project_dir
            / "instance"
            / "uploads"
        )
    else:
        upload_root = Path(
            uploads_root
        )

    upload_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging_root = (
        upload_root.parent
        / "_staging"
    )

    staging_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    task_service = TaskService(
        database,
        software_version="1.0",
    )

    validation_service = (
        ValidationService(
            database,
            uploads_root=upload_root,
        )
    )

    readiness_service = (
        ReadinessService(database)
    )

    firms_processing_service = (
        FirmsProcessingService(
            database
        )
    )

    mcd64_processing_service = (
        Mcd64ProcessingService(
            database
        )
    )

    statistics_service = (
        StatisticsService(
            database
        )
    )

    baseline_path = (
        Path(historical_baseline_path)
        if historical_baseline_path is not None
        else (
            settings.project_dir
            / "data"
            / "baselines"
            / "firms_noaa20_daily.json"
        )
    )

    historical_baseline_service = (
        HistoricalFirmsBaselineService(
            baseline_path
        )
    )

    risk_assessment_service = (
        RiskAssessmentService(
            database,
            statistics_service,
        )
    )

    auto_analysis_service = AutoAnalysisService(
        task_service=task_service,
        validation_service=validation_service,
        readiness_service=readiness_service,
        firms_processing_service=firms_processing_service,
        mcd64_processing_service=mcd64_processing_service,
    )

    app = Flask(
        __name__,
        template_folder=str(
            settings.project_dir
            / "templates"
        ),
        static_folder=str(
            settings.project_dir
            / "static"
        ),
    )

    app.config.update(
        TESTING=testing,
    )

    app.json.ensure_ascii = False

    app.extensions[
        "fire_database"
    ] = database

    app.extensions[
        "task_service"
    ] = task_service

    app.extensions[
        "validation_service"
    ] = validation_service

    app.extensions[
        "readiness_service"
    ] = readiness_service

    app.extensions[
        "firms_processing_service"
    ] = firms_processing_service

    app.extensions[
        "mcd64_processing_service"
    ] = mcd64_processing_service

    app.extensions[
        "statistics_service"
    ] = statistics_service

    app.extensions[
        "historical_baseline_service"
    ] = historical_baseline_service

    app.extensions[
        "risk_assessment_service"
    ] = risk_assessment_service

    app.extensions[
        "auto_analysis_service"
    ] = auto_analysis_service

    def query_args() -> tuple[
        str | None,
        str | None,
        str | None,
    ]:
        region = (
            request.args.get("region")
            or None
        )

        start = _as_optional_date(
            request.args.get("start")
        )

        end = _as_optional_date(
            request.args.get("end")
        )

        if (
            start
            and end
            and start > end
        ):
            raise ValueError(
                "开始日期不能晚于结束日期。"
            )

        known = {
            item["name"]
            for item
            in database.list_regions()
        }

        if (
            region
            and region not in known
        ):
            raise ValueError(
                "所选区域尚未导入"
                "行政区边界。"
            )

        return (
            region,
            start,
            end,
        )

    def build_analysis_summary(
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

    def render_task_detail(
        task_id: str,
        *,
        page_error: str | None = None,
        http_status: int = 200,
    ):
        task = (
            task_service
            .get_task(task_id)
        )

        if task is None:
            return (
                "分析任务不存在。",
                404,
            )

        files = (
            database
            .list_input_files(task_id)
        )

        readiness = (
            readiness_service
            .evaluate_task(task_id)
        )

        firms_input_files = [
            item
            for item in files
            if (
                item["file_role"]
                == "firms_csv"
                and item[
                    "validation_status"
                ]
                in {
                    "valid",
                    "valid_with_warnings",
                }
            )
        ]

        firms_runs = (
            database.list_import_runs(
                task_id=task_id,
                data_kind=(
                    "active_fire_observations"
                ),
                limit=20,
            )
        )

        mcd64_pairs = (
            (
                    readiness.details
                    or {}
            ).get(
                "mcd64_pairs",
                [],
            )
        )

        mcd64_runs = (
            database.list_import_runs(
                task_id=task_id,
                data_kind=(
                    "burned_pixels_tif"
                ),
                limit=20,
            )
        )

        region_count = len(
            database.list_regions()
        )

        task_region_statistics = (
            statistics_service
            .task_region_statistics(
                task_id
            )
        )

        task_daily_series = (
            statistics_service
            .task_daily_series(task_id)
        )

        analysis_summary = (
            build_analysis_summary(task)
        )

        region_feature_collection = (
            database.region_feature_collection()
        )

        task_region_ranking = sorted(
            task_region_statistics,
            key=lambda row: (
                int(row.get("active_fire_count", 0)),
                float(row.get("burned_area_km2", 0.0)),
            ),
            reverse=True,
        )

        has_completed_processing = (
                any(
                    run["status"] == "completed"
                    for run in firms_runs
                )
                or any(
            run["status"] == "completed"
            for run in mcd64_runs
        )
        )

        task_risk_assessment = (
            risk_assessment_service
            .assess_task(
                task_id
            )
            if has_completed_processing
            else None
        )


        task_firms_observations = (
            statistics_service
            .task_firms_observations(
                task_id
            )
        )

        firms_intelligence = (
            FirmsIntelligenceService()
            .analyze(
                task_firms_observations
            )
            .as_dict()
        )

        historical_baseline = (
            historical_baseline_service
            .compare(
                task_firms_observations,
                analysis_start=task.get(
                    "analysis_start"
                ),
                analysis_end=task.get(
                    "analysis_end"
                ),
            )
        )

        return (
            render_template(
                "task_detail.html",
                task=task,
                task_id=task_id,
                files=files,
                readiness=readiness,
                scope_labels=SCOPE_LABELS,
                file_role_labels=(
                    FILE_ROLE_LABELS
                ),
                page_error=page_error,
                firms_input_files=(
                    firms_input_files
                ),
                firms_runs=(
                    firms_runs
                ),
                mcd64_pairs=(
                    mcd64_pairs
                ),
                mcd64_runs=(
                    mcd64_runs
                ),
                region_count=(
                    region_count
                ),
                task_region_statistics=(
                    task_region_statistics
                ),
                task_risk_assessment=(
                    task_risk_assessment
                ),
                analysis_summary=(
                    analysis_summary
                ),
                task_daily_series=(
                    task_daily_series
                ),
                task_region_ranking=(
                    task_region_ranking
                ),
                firms_intelligence=(
                    firms_intelligence
                ),
                historical_baseline=(
                    historical_baseline
                ),
                region_feature_collection=(
                    region_feature_collection
                ),
            ),
            http_status,
        )

    @app.get("/")
    def index():
        return render_home()

    @app.post("/analyze")
    def analyze_uploads():
        uploaded_files = [
            item
            for item in request.files.getlist("files")
            if item is not None and item.filename
        ]

        if not uploaded_files:
            return render_home(
                page_error="请选择需要分析的数据文件。",
                http_status=400,
            )

        try:
            with tempfile.TemporaryDirectory(
                prefix="fire-auto-upload-",
                dir=staging_root,
            ) as temporary_dir:
                staged_uploads = []

                for index, uploaded in enumerate(uploaded_files, start=1):
                    raw_filename = uploaded.filename.replace("\\", "/")
                    original_filename = Path(raw_filename).name
                    safe_name = secure_filename(original_filename)

                    if not safe_name:
                        suffix = Path(original_filename).suffix.lower()
                        safe_name = f"uploaded_{index}{suffix}"

                    temporary_path = Path(temporary_dir) / f"{index:02d}_{safe_name}"
                    uploaded.save(temporary_path)
                    staged_uploads.append(
                        StagedUpload(
                            path=temporary_path,
                            original_filename=original_filename,
                        )
                    )

                result = auto_analysis_service.create_and_process(staged_uploads)

        except AutoAnalysisProcessingError as exc:
            return render_task_detail(
                exc.task_id,
                page_error=(
                    "文件已经完成识别，但自动分析失败："
                    + str(exc)
                ),
                http_status=400,
            )
        except (ValueError, KeyError, FileNotFoundError, OSError) as exc:
            return render_home(
                page_error=str(exc),
                http_status=400,
            )

        return redirect(
            url_for(
                "task_detail",
                task_id=result["task_id"],
            )
        )

    # =====================================================
    # 分析任务页面
    # =====================================================

    def _record_management_redirect():
        target = request.form.get("return_to", "tasks")
        if target == "home":
            return redirect(url_for("index"))
        return redirect(url_for("tasks"))

    @app.post("/tasks/<task_id>/rename")
    def rename_task_record(task_id: str):
        name = request.form.get("name", "").strip()
        try:
            task_service.rename_task(
                task_id,
                name,
            )
        except (ValueError, KeyError) as exc:
            return str(exc), 400

        return _record_management_redirect()

    @app.post("/tasks/<task_id>/delete")
    def delete_task_record(task_id: str):
        try:
            task_service.hide_task(
                task_id
            )
        except KeyError as exc:
            return str(exc), 404

        return _record_management_redirect()


    @app.get("/api/tasks/<task_id>/map-data")
    def task_map_data(task_id: str):
        task = task_service.get_task(
            task_id
        )

        if task is None:
            return jsonify(
                {
                    "error": "analysis record not found",
                }
            ), 404

        rows = (
            statistics_service
            .task_firms_observations(
                task_id
            )
        )

        dates = sorted(
            {
                str(row.get("acquired_date"))
                for row in rows
                if row.get("acquired_date")
            }
        )

        regions = sorted(
            {
                str(row.get("region_name"))
                for row in rows
                if row.get("region_name")
            }
        )

        date_index = {
            value: index
            for index, value in enumerate(
                dates
            )
        }

        region_index = {
            value: index
            for index, value in enumerate(
                regions
            )
        }

        frp_values = sorted(
            float(row["frp"])
            for row in rows
            if row.get("frp") is not None
        )

        frp_p90 = None

        if frp_values:
            percentile_index = min(
                len(frp_values) - 1,
                int(
                    len(frp_values)
                    * 0.90
                ),
            )
            frp_p90 = round(
                frp_values[
                    percentile_index
                ],
                3,
            )

        points = []

        for row in rows:
            acquired_date = str(
                row.get(
                    "acquired_date"
                )
                or ""
            )

            region_name = str(
                row.get(
                    "region_name"
                )
                or ""
            )

            frp = row.get("frp")

            points.append(
                [
                    round(
                        float(
                            row["longitude"]
                        ),
                        5,
                    ),
                    round(
                        float(
                            row["latitude"]
                        ),
                        5,
                    ),
                    date_index.get(
                        acquired_date,
                        -1,
                    ),
                    region_index.get(
                        region_name,
                        -1,
                    ),
                    (
                        round(
                            float(frp),
                            2,
                        )
                        if frp is not None
                        else None
                    ),
                ]
            )

        return jsonify(
            {
                "dates": dates,
                "regions": regions,
                "points": points,
                "frp_p90": frp_p90,
                "point_count": len(points),
            }
        )

    @app.get("/tasks")
    def tasks():
        task_rows = (
            task_service.list_tasks()
        )

        return render_template(
            "tasks.html",
            tasks=task_rows,
            records=build_analysis_records(task_rows),
            scope_labels=SCOPE_LABELS,
            page_error=None,
        )

    @app.post("/tasks")
    def create_task():
        name = (
            request.form
            .get("name", "")
            .strip()
        )

        analysis_start = (
            request.form
            .get(
                "analysis_start",
                "",
            )
            .strip()
            or None
        )

        analysis_end = (
            request.form
            .get(
                "analysis_end",
                "",
            )
            .strip()
            or None
        )

        analysis_scope = (
            request.form
            .get(
                "analysis_scope",
                "",
            )
            .strip()
        )

        try:
            if (
                analysis_scope
                not in
                SUPPORTED_ANALYSIS_SCOPES
            ):
                raise ValueError(
                    "请选择有效的分析范围。"
                )

            task = (
                task_service
                .create_task(
                    name,
                    analysis_start=(
                        analysis_start
                    ),
                    analysis_end=(
                        analysis_end
                    ),
                    parameters={
                        "analysis_scope": (
                            analysis_scope
                        )
                    },
                )
            )

        except ValueError as exc:
            return (
                render_template(
                    "tasks.html",
                    tasks=(
                        task_service
                        .list_tasks()
                    ),
                    scope_labels=(
                        SCOPE_LABELS
                    ),
                    page_error=str(exc),
                ),
                400,
            )

        return redirect(
            url_for(
                "task_detail",
                task_id=(
                    task["task_id"]
                ),
            )
        )

    @app.get(
        "/tasks/<task_id>"
    )
    def task_detail(
        task_id: str,
    ):
        return render_task_detail(
            task_id
        )

    @app.post(
        "/tasks/<task_id>/files"
    )
    def upload_task_file(
        task_id: str,
    ):
        task = (
            task_service
            .get_task(task_id)
        )

        if task is None:
            return (
                "分析任务不存在。",
                404,
            )

        file_role = (
            request.form
            .get("file_role", "")
            .strip()
        )

        uploaded = (
            request.files.get("file")
        )

        if (
            uploaded is None
            or not uploaded.filename
        ):
            return render_task_detail(
                task_id,
                page_error=(
                    "请选择需要上传的文件。"
                ),
                http_status=400,
            )

        raw_filename = (
            uploaded.filename
            .replace("\\", "/")
        )

        original_filename = (
            Path(raw_filename).name
        )

        safe_name = secure_filename(
            original_filename
        )

        if not safe_name:
            suffix = (
                Path(
                    original_filename
                )
                .suffix
                .lower()
            )

            safe_name = (
                "uploaded_file"
                + suffix
            )

        try:
            with tempfile.TemporaryDirectory(
                prefix="fire-upload-",
                dir=staging_root,
            ) as temporary_dir:
                temporary_path = (
                    Path(
                        temporary_dir
                    )
                    / safe_name
                )

                uploaded.save(
                    temporary_path
                )

                validation_service.receive_local_file(
                    task_id=task_id,
                    source_path=(
                        temporary_path
                    ),
                    file_role=file_role,
                    original_filename=(
                        original_filename
                    ),
                )

            readiness_service.evaluate_and_sync_status(
                task_id
            )

        except (
            ValueError,
            KeyError,
            FileNotFoundError,
            OSError,
        ) as exc:
            return render_task_detail(
                task_id,
                page_error=str(exc),
                http_status=400,
            )

        return redirect(
            url_for(
                "task_detail",
                task_id=task_id,
            )
        )

    @app.post(
        "/tasks/<task_id>/readiness"
    )
    def refresh_task_readiness(
        task_id: str,
    ):
        try:
            readiness_service.evaluate_and_sync_status(
                task_id
            )

        except KeyError:
            return (
                "分析任务不存在。",
                404,
            )

        return redirect(
            url_for(
                "task_detail",
                task_id=task_id,
            )
        )

    @app.post(
        "/tasks/<task_id>/process/firms"
    )
    def process_task_firms(
            task_id: str,
    ):
        task = (
            task_service
            .get_task(task_id)
        )

        if task is None:
            return (
                "分析任务不存在。",
                404,
            )

        try:
            firms_processing_service.process_task(
                task_id,
                quality_only=True,
            )

        except (
                ValueError,
                KeyError,
                FileNotFoundError,
                RuntimeError,
                OSError,
        ) as exc:
            return render_task_detail(
                task_id,
                page_error=(
                        "FIRMS 处理失败："
                        + str(exc)
                ),
                http_status=400,
            )

        return redirect(
            url_for(
                "task_detail",
                task_id=task_id,
            )
        )

    @app.post(
        "/tasks/<task_id>/process/mcd64"
    )
    def process_task_mcd64(task_id: str):
        # FIRMS-only V1: MCD64A1 is intentionally not exposed as a web feature.
        # Legacy storage/service code may remain for backward compatibility.
        return ("", 404)

    # =====================================================
    # 原有统计查询 API
    # =====================================================

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": (
                    "heilongjiang-"
                    "fire-data-risk-platform"
                ),
                "database": str(
                    settings.database_path
                ),
                "data": (
                    database.data_status()
                ),
            }
        )

    @app.get("/api/regions")
    def regions():
        return jsonify(
            {
                "regions": [
                    {
                        "name": row[
                            "name"
                        ],
                        "level": row[
                            "level"
                        ],
                    }
                    for row
                    in database.list_regions()
                ]
            }
        )

    @app.get("/api/status")
    def status():
        return jsonify(
            database.data_status()
        )

    @app.get("/api/summary")
    def summary():
        region, start, end = (
            query_args()
        )

        return jsonify(
            database.summary(
                region,
                start,
                end,
            )
        )

    @app.get("/api/statistics/regions")
    def statistics_regions():

        return jsonify(
            {
                "regions": (
                    statistics_service
                    .region_statistics()
                )
            }
        )


    @app.get("/api/statistics/ranking")
    def statistics_ranking():

        metric = (
            request.args.get(
                "metric",
                "burned_area_km2",
            )
        )

        limit = int(
            request.args.get(
                "limit",
                "10",
            )
        )

        return jsonify(
            {
                "metric": metric,
                "ranking": (
                    statistics_service
                    .region_ranking(
                        metric=metric,
                        limit=limit,
                    )
                ),
            }
        )

    @app.get("/api/daily")
    def daily():
        region, start, end = (
            query_args()
        )

        return jsonify(
            {
                "region": (
                    region
                    or "全部已导入区域"
                ),
                "series": (
                    database.daily_series(
                        region,
                        start,
                        end,
                    )
                ),
            }
        )

    @app.get("/api/map")
    def map_data():
        region, start, end = (
            query_args()
        )

        raw_limit = (
            request.args.get(
                "limit",
                "2000",
            )
        )

        try:
            limit = max(
                1,
                min(
                    int(raw_limit),
                    5000,
                ),
            )

        except ValueError as exc:
            raise ValueError(
                "limit 必须是 "
                "1 到 5000 的整数。"
            ) from exc

        payload = (
            database.map_records(
                region,
                start,
                end,
                limit,
            )
        )

        payload["boundary"] = (
            database
            .region_feature_collection(
                region
            )
        )

        payload["limit"] = limit

        return jsonify(payload)

    @app.get(
        "/tasks/<task_id>/export.csv"
    )
    def export_task_csv(
            task_id: str,
    ):
        task = (
            task_service
            .get_task(task_id)
        )

        if task is None:
            return (
                "分析任务不存在。",
                404,
            )

        firms_runs = (
            database.list_import_runs(
                task_id=task_id,
                data_kind=(
                    "active_fire_observations"
                ),
                limit=50,
            )
        )

        mcd64_runs = (
            database.list_import_runs(
                task_id=task_id,
                data_kind=(
                    "burned_pixels_tif"
                ),
                limit=50,
            )
        )

        has_completed_processing = (
                any(
                    run["status"] == "completed"
                    for run in firms_runs
                )
                or any(
            run["status"] == "completed"
            for run in mcd64_runs
        )
        )

        if not has_completed_processing:
            raise ValueError(
                "当前任务尚未完成 FIRMS "
                "或 MCD64A1 正式处理，"
                "暂不能导出任务风险评估结果。"
            )

        assessment = (
            risk_assessment_service
            .assess_task(
                task_id
            )
        )

        buffer = StringIO(
            newline=""
        )

        writer = csv.writer(
            buffer
        )

        # -----------------------------
        # 任务与规则说明
        # -----------------------------

        writer.writerow(
            [
                "数据说明",
                "值",
            ]
        )

        writer.writerow(
            [
                "分析任务 ID",
                task_id,
            ]
        )

        writer.writerow(
            [
                "评估类型",
                "任务内相对火情关注等级",
            ]
        )

        writer.writerow(
            [
                "规则标识",
                assessment[
                    "rule_id"
                ],
            ]
        )

        writer.writerow(
            [
                "规则版本",
                assessment[
                    "rule_version"
                ],
            ]
        )

        writer.writerow(
            [
                "评估范围",
                "当前分析任务内行政区相对比较",
            ]
        )

        writer.writerow(
            [
                "重要说明",
                assessment[
                    "disclaimer"
                ],
            ]
        )

        writer.writerow([])

        # -----------------------------
        # 行政区评估结果
        # -----------------------------

        writer.writerow(
            [
                "行政区",
                "FIRMS 主动火点观测记录数",
                "MCD64A1 烧毁像元数",
                "MCD64A1 烧毁像元面积估计 km²",
                "FIRMS 相对位置",
                "MCD64A1 面积相对位置",
                "相对分值",
                "相对关注等级",
                "评估说明",
            ]
        )

        for item in assessment[
            "regions"
        ]:
            writer.writerow(
                [
                    item[
                        "region_name"
                    ],
                    item[
                        "active_fire_count"
                    ],
                    item[
                        "burned_pixel_count"
                    ],
                    item[
                        "burned_area_km2"
                    ],
                    (
                        item[
                            "active_fire_relative_position"
                        ]
                        if item[
                               "active_fire_relative_position"
                           ]
                           is not None
                        else ""
                    ),
                    (
                        item[
                            "burned_area_relative_position"
                        ]
                        if item[
                               "burned_area_relative_position"
                           ]
                           is not None
                        else ""
                    ),
                    (
                        item[
                            "relative_score"
                        ]
                        if item[
                               "relative_score"
                           ]
                           is not None
                        else ""
                    ),
                    item[
                        "attention_level"
                    ],
                    item[
                        "explanation"
                    ],
                ]
            )

        filename = (
            f"fire_monitor_task_"
            f"{task_id}.csv"
        )

        return Response(
            "\ufeff"
            + buffer.getvalue(),
            content_type=(
                "text/csv; "
                "charset=utf-8"
            ),
            headers={
                "Content-Disposition": (
                    'attachment; '
                    f'filename="{filename}"'
                )
            },
        )

    @app.get("/api/export.csv")
    def export_csv():
        region, start, end = (
            query_args()
        )

        summary_data = (
            database.summary(
                region,
                start,
                end,
            )
        )

        daily_rows = (
            database.daily_series(
                region,
                start,
                end,
            )
        )

        buffer = StringIO(
            newline=""
        )

        writer = csv.writer(
            buffer
        )

        writer.writerow(
            ["数据说明", "值"]
        )

        writer.writerow(
            [
                "查询区域",
                summary_data[
                    "region"
                ],
            ]
        )

        writer.writerow(
            [
                "开始日期",
                start
                or "全部已导入时段",
            ]
        )

        writer.writerow(
            [
                "结束日期",
                end
                or "全部已导入时段",
            ]
        )

        writer.writerow(
            [
                "主动火点观测记录数",
                summary_data[
                    "active_fire_observation_count"
                ],
            ]
        )

        writer.writerow(
            [
                "烧毁像元数",
                summary_data[
                    "burned_pixel_count"
                ],
            ]
        )

        writer.writerow(
            [
                "火烧迹地面积_km2",
                summary_data[
                    "burned_area_km2"
                ],
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "日期",
                "主动火点观测记录数",
                "烧毁像元数",
                "火烧迹地面积_km2",
            ]
        )

        for row in daily_rows:
            writer.writerow(
                [
                    row["date"],
                    row[
                        "active_fire_observation_count"
                    ],
                    row[
                        "burned_pixel_count"
                    ],
                    row[
                        "burned_area_km2"
                    ],
                ]
            )

        filename = (
            "fire_monitor_export.csv"
        )

        return Response(
            "\ufeff"
            + buffer.getvalue(),
            content_type=(
                "text/csv; "
                "charset=utf-8"
            ),
            headers={
                "Content-Disposition": (
                    'attachment; '
                    f'filename="{filename}"'
                )
            },
        )

    @app.errorhandler(ValueError)
    def handle_value_error(
        error: ValueError,
    ):
        return (
            jsonify(
                {
                    "error": (
                        "invalid_request"
                    ),
                    "message": str(
                        error
                    ),
                }
            ),
            400,
        )

    @app.errorhandler(Exception)
    def handle_exception(
            error: Exception,
    ):
        # Flask / Werkzeug 自己产生的 4xx / 5xx HTTP 异常
        # 保留原始 HTTP 状态码，不统一包装成 500。
        if isinstance(error, HTTPException):
            return error

        if app.config["TESTING"]:
            raise error

        return (
            jsonify(
                {
                    "error": (
                        type(error)
                        .__name__
                    ),
                    "message": str(
                        error
                    ),
                }
            ),
            500,
        )

    return app