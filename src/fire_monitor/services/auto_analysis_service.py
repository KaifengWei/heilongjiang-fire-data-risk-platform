# FIRMS CSV 自动识别、建档与分析。

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from fire_monitor.core.file_validation import ValidationResult, validate_firms_csv
from fire_monitor.services.firms_processing_service import FirmsProcessingService
from fire_monitor.services.import_service import read_csv_with_fallback
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
    def __init__(
        self,
        *,
        task_service: TaskService,
        validation_service: ValidationService,
        readiness_service: ReadinessService,
        firms_processing_service: FirmsProcessingService,
        mcd64_processing_service: Any | None = None,
    ):
        self.task_service = task_service
        self.validation_service = validation_service
        self.readiness_service = readiness_service
        self.firms_processing_service = firms_processing_service
        self._legacy_mcd64_processing_service = mcd64_processing_service

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

    def _detect_one(self, upload: StagedUpload) -> DetectedUpload:
        if upload.path.suffix.lower() != ".csv":
            raise ValueError(
                f"{upload.original_filename} 不是 CSV 文件。"
                "当前版本只需要上传从 NASA FIRMS 下载并解压后的 CSV。"
            )

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

    @staticmethod
    def _task_name(start: str | None, end: str | None) -> str:
        if start and end:
            period = start if start == end else f"{start} 至 {end}"
            return f"{period} FIRMS 火点分析"
        return "自动识别 FIRMS 火点分析"

    def inspect(self, uploads: list[StagedUpload]) -> AnalysisInspection:
        if not uploads:
            raise ValueError("请选择需要分析的 FIRMS CSV。")

        detected = tuple(self._detect_one(item) for item in uploads)
        starts = [item.date_start for item in detected if item.date_start]
        ends = [item.date_end for item in detected if item.date_end]

        analysis_start = min(starts) if starts else None
        analysis_end = max(ends) if ends else None

        return AnalysisInspection(
            files=detected,
            analysis_scope="firms_only",
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            task_name=self._task_name(analysis_start, analysis_end),
        )

    def create_and_process(self, uploads: list[StagedUpload]) -> dict[str, Any]:
        inspection = self.inspect(uploads)

        task = self.task_service.create_task(
            inspection.task_name,
            analysis_start=inspection.analysis_start,
            analysis_end=inspection.analysis_end,
            assessment_mode="relative_attention",
            parameters={
                "analysis_scope": "firms_only",
                "auto_analysis": True,
                "detected_roles": ["firms_csv"],
            },
        )
        task_id = task["task_id"]

        try:
            for item in inspection.files:
                self.validation_service.receive_local_file(
                    task_id=task_id,
                    source_path=item.path,
                    file_role="firms_csv",
                    original_filename=item.original_filename,
                )

            self.readiness_service.evaluate_and_sync_status(task_id)
            report = self.firms_processing_service.process_task(
                task_id,
                quality_only=True,
            )
            self.task_service.mark_completed(task_id)

            return {
                "task_id": task_id,
                "inspection": inspection,
                "reports": {"firms": report},
            }

        except Exception as exc:
            self.task_service.mark_failed(task_id, str(exc))
            raise AutoAnalysisProcessingError(task_id, str(exc)) from exc
