"""分析任务输入数据准备状态判断。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fire_monitor.core.mcd64_validation import (
    validate_mcd64_pair,
)
from fire_monitor.storage.database import Database


SUPPORTED_ANALYSIS_SCOPES = {
    "firms_only",
    "mcd64_only",
    "combined",
}

ACCEPTED_VALIDATION_STATUSES = {
    "valid",
    "valid_with_warnings",
}


@dataclass
class TaskReadinessResult:
    """分析任务输入准备状态。"""

    ready: bool
    analysis_scope: str
    reasons: list[str]
    warnings: list[str]
    details: dict[str, Any]

    @property
    def status(self) -> str:
        if self.ready:
            return "ready"

        return "not_ready"


class ReadinessService:
    """判断分析任务是否具备进入后续处理的基本输入条件。"""

    def __init__(
        self,
        database: Database,
    ):
        self.database = database
        self.database.initialize()

    @staticmethod
    def _validation_metadata(
        record: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = (
            record.get("metadata")
            or {}
        )

        validation = metadata.get(
            "validation"
        )

        if isinstance(
            validation,
            dict,
        ):
            return validation

        return {}

    @staticmethod
    def _product_key(
        record: dict[str, Any],
    ) -> tuple[int, int] | None:
        metadata = (
            ReadinessService
            ._validation_metadata(record)
        )

        year = metadata.get("year")
        doy = metadata.get(
            "month_start_doy"
        )

        if year is None or doy is None:
            return None

        try:
            return (
                int(year),
                int(doy),
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _path_exists(
        record: dict[str, Any],
    ) -> bool:
        stored_path = record.get(
            "stored_path"
        )

        if not stored_path:
            return False

        return Path(
            stored_path
        ).is_file()

    def _usable_records(
        self,
        records: list[dict[str, Any]],
        *,
        file_role: str,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        role_records = [
            item
            for item in records
            if item["file_role"]
            == file_role
        ]

        invalid_count = sum(
            1
            for item in role_records
            if item[
                "validation_status"
            ]
            == "invalid"
        )

        if invalid_count:
            warnings.append(
                f"{file_role} 存在 "
                f"{invalid_count} 个"
                "未通过校验的文件"
            )

        usable: list[
            dict[str, Any]
        ] = []

        for item in role_records:
            status = item[
                "validation_status"
            ]

            if (
                status
                not in
                ACCEPTED_VALIDATION_STATUSES
            ):
                continue

            if not self._path_exists(
                item
            ):
                warnings.append(
                    f"{file_role} 文件"
                    f" {item['id']} "
                    "已登记但本地文件不存在"
                )
                continue

            if (
                status
                == "valid_with_warnings"
            ):
                message = (
                    item.get(
                        "validation_message"
                    )
                    or "存在校验警告"
                )

                warnings.append(
                    f"{file_role}：{message}"
                )

            usable.append(item)

        return usable

    @staticmethod
    def _group_by_product_date(
        records: list[dict[str, Any]],
    ) -> tuple[
        dict[
            tuple[int, int],
            list[dict[str, Any]],
        ],
        list[int],
    ]:
        grouped: dict[
            tuple[int, int],
            list[dict[str, Any]],
        ] = {}

        missing_metadata_ids: list[int] = []

        for record in records:
            key = (
                ReadinessService
                ._product_key(record)
            )

            if key is None:
                missing_metadata_ids.append(
                    int(record["id"])
                )
                continue

            grouped.setdefault(
                key,
                [],
            ).append(record)

        return (
            grouped,
            missing_metadata_ids,
        )

    def evaluate_task(
        self,
        task_id: str,
        *,
        analysis_scope: str | None = None,
    ) -> TaskReadinessResult:
        """计算任务当前是否具备基本输入条件。

        analysis_scope:
        - firms_only
        - mcd64_only
        - combined

        若未显式指定，则读取任务 parameters.analysis_scope；
        旧任务没有该字段时默认 combined。
        """

        task = (
            self.database
            .get_analysis_task(task_id)
        )

        if task is None:
            raise KeyError(
                f"分析任务不存在：{task_id}"
            )

        if analysis_scope is None:
            parameters = (
                task.get("parameters")
                or {}
            )

            analysis_scope = (
                parameters.get(
                    "analysis_scope",
                    "combined",
                )
            )

        if (
            analysis_scope
            not in
            SUPPORTED_ANALYSIS_SCOPES
        ):
            return TaskReadinessResult(
                ready=False,
                analysis_scope=str(
                    analysis_scope
                ),
                reasons=[
                    "任务使用了不支持的"
                    f"分析范围：{analysis_scope}"
                ],
                warnings=[],
                details={},
            )

        records = (
            self.database
            .list_input_files(task_id)
        )

        reasons: list[str] = []
        warnings: list[str] = []

        details: dict[str, Any] = {
            "file_count": len(records),
            "mcd64_pairs": [],
        }

        requires_firms = (
            analysis_scope
            in {
                "firms_only",
                "combined",
            }
        )

        requires_mcd64 = (
            analysis_scope
            in {
                "mcd64_only",
                "combined",
            }
        )

        firms_files = (
            self._usable_records(
                records,
                file_role="firms_csv",
                warnings=warnings,
            )
        )

        burn_files = (
            self._usable_records(
                records,
                file_role=(
                    "mcd64_burn_date"
                ),
                warnings=warnings,
            )
        )

        qa_files = (
            self._usable_records(
                records,
                file_role="mcd64_qa",
                warnings=warnings,
            )
        )

        details["usable_files"] = {
            "firms_csv": len(
                firms_files
            ),
            "mcd64_burn_date": len(
                burn_files
            ),
            "mcd64_qa": len(
                qa_files
            ),
        }

        if (
            requires_firms
            and not firms_files
        ):
            reasons.append(
                "缺少至少一个通过基础校验的 "
                "FIRMS CSV 文件"
            )

        if requires_mcd64:
            if not burn_files:
                reasons.append(
                    "缺少至少一个通过基础校验的 "
                    "MCD64A1 Burn Date 文件"
                )

            if not qa_files:
                reasons.append(
                    "缺少至少一个通过基础校验的 "
                    "MCD64A1 QA 文件"
                )

            (
                burn_groups,
                burn_missing_metadata,
            ) = (
                self._group_by_product_date(
                    burn_files
                )
            )

            (
                qa_groups,
                qa_missing_metadata,
            ) = (
                self._group_by_product_date(
                    qa_files
                )
            )

            if burn_missing_metadata:
                reasons.append(
                    "部分 Burn Date 文件缺少"
                    "可识别的产品日期元数据："
                    + ", ".join(
                        str(value)
                        for value
                        in burn_missing_metadata
                    )
                )

            if qa_missing_metadata:
                reasons.append(
                    "部分 QA 文件缺少"
                    "可识别的产品日期元数据："
                    + ", ".join(
                        str(value)
                        for value
                        in qa_missing_metadata
                    )
                )

            burn_keys = set(
                burn_groups
            )

            qa_keys = set(
                qa_groups
            )

            for key in sorted(
                burn_keys - qa_keys
            ):
                year, doy = key

                reasons.append(
                    f"A{year:04d}{doy:03d} "
                    "存在 Burn Date，"
                    "但缺少对应 QA"
                )

            for key in sorted(
                qa_keys - burn_keys
            ):
                year, doy = key

                reasons.append(
                    f"A{year:04d}{doy:03d} "
                    "存在 QA，"
                    "但缺少对应 Burn Date"
                )

            for key in sorted(
                burn_keys & qa_keys
            ):
                year, doy = key

                burn_candidates = (
                    burn_groups[key]
                )

                qa_candidates = (
                    qa_groups[key]
                )

                if (
                    len(burn_candidates)
                    != 1
                ):
                    reasons.append(
                        f"A{year:04d}{doy:03d} "
                        "存在多个 Burn Date 文件，"
                        "当前版本无法确定唯一配对"
                    )
                    continue

                if (
                    len(qa_candidates)
                    != 1
                ):
                    reasons.append(
                        f"A{year:04d}{doy:03d} "
                        "存在多个 QA 文件，"
                        "当前版本无法确定唯一配对"
                    )
                    continue

                burn_record = (
                    burn_candidates[0]
                )

                qa_record = (
                    qa_candidates[0]
                )

                pair_result = (
                    validate_mcd64_pair(
                        burn_record[
                            "stored_path"
                        ],
                        qa_record[
                            "stored_path"
                        ],
                    )
                )

                if not pair_result.accepted:
                    reasons.append(
                        f"A{year:04d}{doy:03d} "
                        "Burn Date / QA "
                        "配对失败："
                        + pair_result.message
                    )
                    continue

                details[
                    "mcd64_pairs"
                ].append(
                    {
                        "product_date": (
                            f"A{year:04d}"
                            f"{doy:03d}"
                        ),
                        "burn_date_file_id": (
                            burn_record["id"]
                        ),
                        "qa_file_id": (
                            qa_record["id"]
                        ),
                        "pair_status": (
                            "valid"
                        ),
                    }
                )

            if (
                burn_files
                and qa_files
                and not details[
                    "mcd64_pairs"
                ]
                and not any(
                    "多个" in reason
                    or "缺少对应" in reason
                    or "配对失败" in reason
                    for reason in reasons
                )
            ):
                reasons.append(
                    "没有形成可用的 "
                    "MCD64A1 Burn Date / QA "
                    "配对"
                )

        return TaskReadinessResult(
            ready=not reasons,
            analysis_scope=(
                analysis_scope
            ),
            reasons=reasons,
            warnings=warnings,
            details=details,
        )

    def evaluate_and_sync_status(
        self,
        task_id: str,
        *,
        analysis_scope: str | None = None,
    ) -> TaskReadinessResult:
        """计算准备状态并同步任务基础状态。

        只修改尚未进入正式计算生命周期的任务：
        created / validating / ready。

        running / completed / failed 不在这里自动修改。
        """

        result = self.evaluate_task(
            task_id,
            analysis_scope=analysis_scope,
        )

        task = (
            self.database
            .get_analysis_task(task_id)
        )

        if task is None:
            raise KeyError(
                f"分析任务不存在：{task_id}"
            )

        if task["status"] in {
            "created",
            "validating",
            "ready",
        }:
            target_status = (
                "ready"
                if result.ready
                else "validating"
            )

            self.database.update_analysis_task_status(
                task_id,
                target_status,
            )

        return result