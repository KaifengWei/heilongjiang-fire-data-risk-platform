"""分析业务服务。"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from fire_monitor.storage.database import Database


VALID_ASSESSMENT_MODES = {
    None,
    "relative_attention",
    "external_rule",
}


class TaskService:
    """负责分析任务的创建和基本状态管理。"""

    def __init__(
        self,
        database: Database,
        *,
        software_version: str = "0.1.1",
    ):
        self.database = database
        self.software_version = software_version
        self.database.initialize()

    @staticmethod
    def _validate_date_range(
        analysis_start: str | None,
        analysis_end: str | None,
    ) -> None:
        if analysis_start is not None:
            date.fromisoformat(analysis_start)

        if analysis_end is not None:
            date.fromisoformat(analysis_end)

        if (
            analysis_start is not None
            and analysis_end is not None
            and analysis_start > analysis_end
        ):
            raise ValueError(
                "分析开始日期不能晚于结束日期"
            )

    def create_task(
        self,
        name: str,
        *,
        analysis_start: str | None = None,
        analysis_end: str | None = None,
        boundary_set_id: str | None = None,
        assessment_mode: str | None = None,
        parameters: dict | None = None,
    ) -> dict:
        """创建新的分析任务。"""

        clean_name = name.strip()

        if not clean_name:
            raise ValueError(
                "任务名称不能为空"
            )

        self._validate_date_range(
            analysis_start,
            analysis_end,
        )

        if assessment_mode not in VALID_ASSESSMENT_MODES:
            raise ValueError(
                f"不支持的评价模式：{assessment_mode}"
            )

        task_id = (
            "TASK-"
            + uuid4().hex[:12].upper()
        )

        return self.database.create_analysis_task(
            task_id=task_id,
            name=clean_name,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            boundary_set_id=boundary_set_id,
            software_version=self.software_version,
            assessment_mode=assessment_mode,
            parameters=parameters,
        )

    def get_task(
        self,
        task_id: str,
    ) -> dict | None:
        return self.database.get_analysis_task(
            task_id
        )

    def list_tasks(
        self,
        limit: int = 100,
    ) -> list[dict]:
        return self.database.list_analysis_tasks(
            limit
        )

    def mark_running(
        self,
        task_id: str,
    ) -> None:
        self.database.update_analysis_task_status(
            task_id,
            "running",
        )

    def mark_completed(
        self,
        task_id: str,
    ) -> None:
        self.database.update_analysis_task_status(
            task_id,
            "completed",
        )

    def mark_failed(
        self,
        task_id: str,
        reason: str,
    ) -> None:
        self.database.update_analysis_task_status(
            task_id,
            "failed",
            error_message=reason,
        )