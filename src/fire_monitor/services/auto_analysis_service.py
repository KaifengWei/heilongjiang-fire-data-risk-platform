"""自动识别用户上传文件并创建一次独立分析记录。"""

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
