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
) -> Flask:
    """创建 Flask 应用。"""

    settings = load_settings(
        database_path
    )

    database = Database(
        settings.database_path
    )
    database.initialize()

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
        software_version="0.1.1",
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

        return (
            render_template(
                "task_detail.html",
                task=task,
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
            ),
            http_status,
        )

    @app.get("/")
    def index():
        return render_template(
            "index.html"
        )

    # =====================================================
    # 分析任务页面
    # =====================================================

    @app.get("/tasks")
    def tasks():
        task_rows = (
            task_service.list_tasks()
        )

        return render_template(
            "tasks.html",
            tasks=task_rows,
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
    def process_task_mcd64(
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

        qa_policy = (
            request.form
            .get(
                "qa_policy",
                "standard",
            )
            .strip()
        )

        if qa_policy not in {
            "standard",
            "strict",
        }:
            return render_task_detail(
                task_id,
                page_error=(
                    "MCD64A1 处理失败："
                    "QA 策略无效。"
                ),
                http_status=400,
            )

        try:
            (
                mcd64_processing_service
                .process_task(
                    task_id,
                    qa_policy=qa_policy,
                )
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
                    "MCD64A1 处理失败："
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