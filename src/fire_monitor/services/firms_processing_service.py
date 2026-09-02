"""任务级 FIRMS 主动火点正式处理服务。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from fire_monitor.core.firms import (
    normalize_firms_dataframe,
)
from fire_monitor.core.geography import (
    RegionIndex,
)
from fire_monitor.services.import_service import (
    read_csv_with_fallback,
)
from fire_monitor.storage.database import (
    Database,
)
from fire_monitor.storage.firms_repository import (
    FirmsRepository,
)


ACCEPTED_FILE_STATUSES = {
    "valid",
    "valid_with_warnings",
}


class FirmsProcessingService:
    """执行分析任务中的 FIRMS 正式处理流程。

    处理对象仍然是“主动火点观测记录”，
    不进行火灾事件聚类或火灾次数推断。
    """

    def __init__(
        self,
        database: Database,
    ):
        self.database = database
        self.database.initialize()

        self.repository = (
            FirmsRepository(database)
        )

    def _get_input_file(
        self,
        *,
        task_id: str,
        input_file_id: int,
    ) -> dict[str, Any]:
        files = (
            self.database
            .list_input_files(task_id)
        )

        for item in files:
            if (
                int(item["id"])
                == int(input_file_id)
            ):
                return item

        raise KeyError(
            f"任务 {task_id} 中不存在"
            f"输入文件 {input_file_id}"
        )

    @staticmethod
    def _firms_source(
        record: dict[str, Any],
    ) -> str:
        """生成用于观测来源字段的基础来源名称。

        浏览器上传阶段当前没有要求用户手工填写
        FIRMS 数据集名称，因此默认使用 FIRMS_USER_UPLOAD。

        NRT / SP 等处理阶段由 CSV 内 version 字段判断，
        原始文件本身则通过 import_run.input_file_id 追溯。
        """

        product_name = (
            record.get("product_name")
            or ""
        ).strip()

        if product_name:
            return product_name

        return "FIRMS_USER_UPLOAD"

    @staticmethod
    def _inside_task_date_range(
        acquired_date: str,
        *,
        start: str | None,
        end: str | None,
    ) -> bool:
        if (
            start is not None
            and acquired_date < start
        ):
            return False

        if (
            end is not None
            and acquired_date > end
        ):
            return False

        return True

    def process_input_file(
        self,
        *,
        task_id: str,
        input_file_id: int,
        quality_only: bool = True,
    ) -> dict[str, Any]:
        """处理一个已经登记的 FIRMS CSV 文件。"""

        task = (
            self.database
            .get_analysis_task(task_id)
        )

        if task is None:
            raise KeyError(
                f"分析任务不存在：{task_id}"
            )

        scope = (
            task.get("parameters")
            or {}
        ).get(
            "analysis_scope",
            "combined",
        )

        if scope not in {
            "firms_only",
            "combined",
        }:
            raise ValueError(
                "当前任务分析范围"
                "不包含 FIRMS 数据处理。"
            )

        record = self._get_input_file(
            task_id=task_id,
            input_file_id=input_file_id,
        )

        if (
            record["file_role"]
            != "firms_csv"
        ):
            raise ValueError(
                "指定输入文件不是 FIRMS CSV。"
            )

        if (
            record["validation_status"]
            not in
            ACCEPTED_FILE_STATUSES
        ):
            raise ValueError(
                "该 FIRMS 文件未通过"
                "输入阶段基础校验。"
            )

        stored_path = (
            record.get("stored_path")
        )

        if not stored_path:
            raise FileNotFoundError(
                "输入文件没有可用的存储路径。"
            )

        source_path = Path(
            stored_path
        )

        if not source_path.is_file():
            raise FileNotFoundError(
                f"FIRMS 文件不存在："
                f"{source_path}"
            )

        regions = (
            self.database
            .list_regions()
        )

        if not regions:
            raise RuntimeError(
                "尚未导入行政区边界，"
                "无法执行 FIRMS 正式空间落区。"
            )

        region_index = (
            RegionIndex(regions)
        )

        firms_source = (
            self._firms_source(record)
        )

        run_id = (
            self.database.start_import(
                "active_fire_observations",
                str(source_path.resolve()),
                metadata={
                    "task_id": task_id,
                    "input_file_id": (
                        input_file_id
                    ),
                    "firms_source": (
                        firms_source
                    ),
                    "quality_only": (
                        quality_only
                    ),
                    "mode": (
                        "task_firms_processing"
                    ),
                },
                task_id=task_id,
                input_file_id=(
                    input_file_id
                ),
            )
        )

        try:
            frame = read_csv_with_fallback(
                source_path,
                low_memory=False,
            )

            normalization = (
                normalize_firms_dataframe(
                    frame,
                    firms_source=(
                        firms_source
                    ),
                    quality_only=(
                        quality_only
                    ),
                    strict_identity=True,
                )
            )

            outside_date_range = 0
            outside_regions = 0

            spatial_rows: list[
                dict[str, Any]
            ] = []

            for row in normalization.rows:
                if not self._inside_task_date_range(
                    row["acquired_date"],
                    start=task.get(
                        "analysis_start"
                    ),
                    end=task.get(
                        "analysis_end"
                    ),
                ):
                    outside_date_range += 1
                    continue

                region_name = (
                    region_index.locate(
                        row["longitude"],
                        row["latitude"],
                    )
                )

                if not region_name:
                    outside_regions += 1
                    continue

                row["region_name"] = (
                    region_name
                )

                spatial_rows.append(
                    row
                )

            # 同一文件内部若完全重复出现同一来源记录，
            # 在进入数据库之前只保留一次。
            #
            # source_record_key 包含：
            # canonical observation + source +
            # processing class + version。
            unique_rows: list[
                dict[str, Any]
            ] = []

            seen_source_keys: set[str] = (
                set()
            )

            duplicate_source_records = 0

            for row in spatial_rows:
                source_key = row[
                    "source_record_key"
                ]

                if (
                    source_key
                    in seen_source_keys
                ):
                    duplicate_source_records += 1
                    continue

                seen_source_keys.add(
                    source_key
                )

                unique_rows.append(
                    row
                )

            processing_classes = Counter(
                (
                    row.get(
                        "processing_class"
                    )
                    or "UNKNOWN"
                )
                for row in unique_rows
            )

            stored = (
                self.repository
                .store_rows(
                    unique_rows,
                    import_run_id=run_id,
                )
            )

            report = {
                "task_id": task_id,
                "input_file_id": (
                    input_file_id
                ),
                "run_id": run_id,
                "original_filename": (
                    record[
                        "original_filename"
                    ]
                ),
                "firms_source": (
                    firms_source
                ),
                "quality_only": (
                    quality_only
                ),

                "input_rows": (
                    normalization
                    .input_rows
                ),

                "normalization_accepted": (
                    normalization
                    .accepted_rows
                ),

                "normalization_rejected": (
                    normalization
                    .rejected_rows
                ),

                "rejection_counts": (
                    normalization
                    .rejection_counts
                ),

                "outside_task_date_range": (
                    outside_date_range
                ),

                "outside_configured_regions": (
                    outside_regions
                ),

                "duplicate_source_records_in_file": (
                    duplicate_source_records
                ),

                "rows_ready_for_storage": (
                    len(unique_rows)
                ),

                "processing_class_counts": (
                    dict(
                        processing_classes
                    )
                ),

                "new_observations": (
                    stored
                    .inserted_observations
                ),

                "existing_observations": (
                    stored
                    .existing_observations
                ),

                "source_records_added": (
                    stored
                    .source_records_added
                ),

                "source_records_existing": (
                    stored
                    .source_records_existing
                ),

                "preferred_source_updates": (
                    stored
                    .preferred_source_updates
                ),
            }

            self.database.finish_import(
                run_id,
                input_count=(
                    normalization
                    .input_rows
                ),
                stored_count=(
                    stored
                    .inserted_observations
                ),
                metadata=report,
            )

            return report

        except Exception as exc:
            self.database.fail_import(
                run_id,
                str(exc),
            )

            raise

    def process_task(
        self,
        task_id: str,
        *,
        quality_only: bool = True,
    ) -> dict[str, Any]:
        """处理任务中全部可用 FIRMS CSV。

        多文件按 input_files.id 顺序执行。
        """

        task = (
            self.database
            .get_analysis_task(task_id)
        )

        if task is None:
            raise KeyError(
                f"分析任务不存在：{task_id}"
            )

        files = [
            item
            for item
            in self.database
            .list_input_files(task_id)
            if (
                item["file_role"]
                == "firms_csv"
                and item[
                    "validation_status"
                ]
                in
                ACCEPTED_FILE_STATUSES
            )
        ]

        if not files:
            raise ValueError(
                "当前任务没有可用于正式处理的"
                " FIRMS CSV 文件。"
            )

        reports: list[
            dict[str, Any]
        ] = []

        for item in files:
            reports.append(
                self.process_input_file(
                    task_id=task_id,
                    input_file_id=(
                        int(item["id"])
                    ),
                    quality_only=(
                        quality_only
                    ),
                )
            )

        return {
            "task_id": task_id,
            "processed_files": (
                len(reports)
            ),
            "reports": reports,
            "new_observations": sum(
                item[
                    "new_observations"
                ]
                for item in reports
            ),
            "existing_observations": sum(
                item[
                    "existing_observations"
                ]
                for item in reports
            ),
            "preferred_source_updates": sum(
                item[
                    "preferred_source_updates"
                ]
                for item in reports
            ),
        }