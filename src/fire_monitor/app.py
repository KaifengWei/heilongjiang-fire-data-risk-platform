"""Flask 应用与只读查询接口。"""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from fire_monitor.config import load_settings
from fire_monitor.storage.database import Database


def _as_optional_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        # ISO 日期字符串可按字典序和 SQLite TEXT 安全比较。
        from datetime import date

        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("日期应为 YYYY-MM-DD，例如 2025-11-01。") from exc


def create_app(database_path: str | Path | None = None, testing: bool = False) -> Flask:
    settings = load_settings(database_path)
    database = Database(settings.database_path)
    database.initialize()
    app = Flask(
        __name__,
        template_folder=str(settings.project_dir / "templates"),
        static_folder=str(settings.project_dir / "static"),
    )
    app.config.update(TESTING=testing)
    app.json.ensure_ascii = False
    app.extensions["fire_database"] = database

    def query_args() -> tuple[str | None, str | None, str | None]:
        region = request.args.get("region") or None
        start = _as_optional_date(request.args.get("start"))
        end = _as_optional_date(request.args.get("end"))
        if start and end and start > end:
            raise ValueError("开始日期不能晚于结束日期。")
        known = {item["name"] for item in database.list_regions()}
        if region and region not in known:
            raise ValueError("所选区域尚未导入行政区边界。")
        return region, start, end

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "heilongjiang-fire-data-risk-platform",
                "database": str(settings.database_path),
                "data": database.data_status(),
            }
        )

    @app.get("/api/regions")
    def regions():
        return jsonify({"regions": [{"name": r["name"], "level": r["level"]} for r in database.list_regions()]})

    @app.get("/api/status")
    def status():
        return jsonify(database.data_status())

    @app.get("/api/summary")
    def summary():
        region, start, end = query_args()
        return jsonify(database.summary(region, start, end))

    @app.get("/api/daily")
    def daily():
        region, start, end = query_args()
        return jsonify({"region": region or "全部已导入区域", "series": database.daily_series(region, start, end)})

    @app.get("/api/map")
    def map_data():
        region, start, end = query_args()
        raw_limit = request.args.get("limit", "2000")
        try:
            limit = max(1, min(int(raw_limit), 5000))
        except ValueError as exc:
            raise ValueError("limit 必须是 1 到 5000 的整数。") from exc
        payload = database.map_records(region, start, end, limit)
        payload["boundary"] = database.region_feature_collection(region)
        payload["limit"] = limit
        return jsonify(payload)

    @app.get("/api/export.csv")
    def export_csv():
        region, start, end = query_args()
        summary_data = database.summary(region, start, end)
        daily_rows = database.daily_series(region, start, end)
        buffer = StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["数据说明", "值"])
        writer.writerow(["查询区域", summary_data["region"]])
        writer.writerow(["开始日期", start or "全部已导入时段"])
        writer.writerow(["结束日期", end or "全部已导入时段"])
        writer.writerow(["主动火点观测记录数", summary_data["active_fire_observation_count"]])
        writer.writerow(["烧毁像元数", summary_data["burned_pixel_count"]])
        writer.writerow(["火烧迹地面积_km2", summary_data["burned_area_km2"]])
        writer.writerow([])
        writer.writerow(["日期", "主动火点观测记录数", "烧毁像元数", "火烧迹地面积_km2"])
        for row in daily_rows:
            writer.writerow(
                [
                    row["date"],
                    row["active_fire_observation_count"],
                    row["burned_pixel_count"],
                    row["burned_area_km2"],
                ]
            )
        filename = "fire_monitor_export.csv"
        return Response(
            "\ufeff" + buffer.getvalue(),
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.errorhandler(ValueError)
    def handle_value_error(error: ValueError):
        return jsonify({"error": "invalid_request", "message": str(error)}), 400

    @app.errorhandler(Exception)
    def handle_exception(error: Exception):
        if app.config["TESTING"]:
            raise error
        return jsonify({"error": type(error).__name__, "message": str(error)}), 500

    return app
