"""任务级 MCD64A1 火烧迹地正式处理服务。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from fire_monitor.core.geography import (
    RegionIndex,
)
from fire_monitor.core.mcd64 import (
    extract_mcd64_burned_pixels,
)
from fire_monitor.core.mcd64_validation import (
    validate_mcd64_pair,
)
from fire_monitor.storage.database import (
    Database,
)
from fire_monitor.storage.mcd64_repository import (
    Mcd64Repository,
)


ACCEPTED_FILE_STATUSES = {
    "valid",
    "valid_with_warnings",
}


class Mcd64ProcessingService:
    """执行分析任务中的 MCD64A1 正式处理。"""

    def __init__(
        self,
        database: Database,
    ):
        self.database = database
        self.database.initialize()

        self.repository = (
            Mcd64Repository(database)
        )

    @staticmethod
    def _validation_metadata(
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """读取输入文件在上传校验阶段保存的元数据。

        input_files.metadata 中的 validation
        是 ValidationService 写入的文件校验结果。

        MCD64A1 的 year、month_start_doy 等
        产品信息均以该校验结果为准。
        """

        metadata = (
            record.get("metadata")
            or {}
        )

        if not isinstance(
            metadata,
            dict,
        ):
            return {}

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
        """读取 MCD64A1 产品年月配对键。"""

        metadata = (
            Mcd64ProcessingService
            ._validation_metadata(
                record
            )
        )

        year = metadata.get(
            "year"
        )

        month_start_doy = (
            metadata.get(
                "month_start_doy"
            )
        )

        if (
            year is None
            or month_start_doy is None
        ):
            return None

        try:
            return (
                int(year),
                int(
                    month_start_doy
                ),
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    def _find_valid_pairs(
        self,
        task_id: str,
    ) -> list[
        tuple[
            dict[str, Any],
            dict[str, Any],
        ]
    ]:
        """查找任务中的有效 Burn Date / QA 配对。"""

        files = (
            self.database
            .list_input_files(task_id)
        )

        burn_by_product: dict[
            tuple[int, int],
            list[dict[str, Any]],
        ] = defaultdict(list)

        qa_by_product: dict[
            tuple[int, int],
            list[dict[str, Any]],
        ] = defaultdict(list)

        for record in files:
            if (
                record[
                    "validation_status"
                ]
                not in
                ACCEPTED_FILE_STATUSES
            ):
                continue

            key = self._product_key(
                record
            )

            if key is None:
                continue

            role = record["file_role"]

            if role == "mcd64_burn_date":
                burn_by_product[
                    key
                ].append(record)

            elif role == "mcd64_qa":
                qa_by_product[
                    key
                ].append(record)

        all_keys = sorted(
            set(burn_by_product)
            | set(qa_by_product)
        )

        pairs: list[
            tuple[
                dict[str, Any],
                dict[str, Any],
            ]
        ] = []

        for key in all_keys:
            burns = burn_by_product.get(
                key,
                [],
            )

            qas = qa_by_product.get(
                key,
                [],
            )

            if (
                len(burns) != 1
                or len(qas) != 1
            ):
                continue

            burn = burns[0]
            qa = qas[0]

            burn_path = Path(
                burn["stored_path"]
            )

            qa_path = Path(
                qa["stored_path"]
            )

            if (
                not burn_path.is_file()
                or not qa_path.is_file()
            ):
                continue

            pair_result = (
                validate_mcd64_pair(
                    burn_path,
                    qa_path,
                )
            )

            if pair_result.accepted:
                pairs.append(
                    (
                        burn,
                        qa,
                    )
                )

        return pairs

    def process_pair(
        self,
        *,
        task_id: str,
        burn_file_id: int,
        qa_file_id: int,
        qa_policy: str = "standard",
    ) -> dict[str, Any]:
        """正式处理一个 Burn Date / QA 文件对。"""

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
            "mcd64_only",
            "combined",
        }:
            raise ValueError(
                "当前任务分析范围"
                "不包含 MCD64A1。"
            )

        files = (
            self.database
            .list_input_files(task_id)
        )

        burn_record = None
        qa_record = None

        for record in files:
            record_id = int(
                record["id"]
            )

            if (
                record_id
                == int(burn_file_id)
            ):
                burn_record = record

            if (
                record_id
                == int(qa_file_id)
            ):
                qa_record = record

        if burn_record is None:
            raise KeyError(
                "任务中不存在指定的 "
                "Burn Date 文件。"
            )

        if qa_record is None:
            raise KeyError(
                "任务中不存在指定的 QA 文件。"
            )

        if (
            burn_record["file_role"]
            != "mcd64_burn_date"
        ):
            raise ValueError(
                "Burn Date 文件角色不正确。"
            )

        if (
            qa_record["file_role"]
            != "mcd64_qa"
        ):
            raise ValueError(
                "QA 文件角色不正确。"
            )

        if (
            burn_record[
                "validation_status"
            ]
            not in
            ACCEPTED_FILE_STATUSES
            or qa_record[
                "validation_status"
            ]
            not in
            ACCEPTED_FILE_STATUSES
        ):
            raise ValueError(
                "Burn Date 或 QA 文件"
                "未通过输入阶段基础校验。"
            )

        burn_path = Path(
            burn_record["stored_path"]
        )

        qa_path = Path(
            qa_record["stored_path"]
        )

        if not burn_path.is_file():
            raise FileNotFoundError(
                f"Burn Date 文件不存在："
                f"{burn_path}"
            )

        if not qa_path.is_file():
            raise FileNotFoundError(
                f"QA 文件不存在："
                f"{qa_path}"
            )

        burn_product_key = (
            self._product_key(
                burn_record
            )
        )

        qa_product_key = (
            self._product_key(
                qa_record
            )
        )

        if (
            burn_product_key is None
            or qa_product_key is None
        ):
            raise ValueError(
                "MCD64A1 文件缺少产品日期元数据。"
            )

        if (
            burn_product_key
            != qa_product_key
        ):
            raise ValueError(
                "Burn Date 与 QA "
                "产品日期不一致。"
            )

        pair_result = (
            validate_mcd64_pair(
                burn_path,
                qa_path,
            )
        )

        if not pair_result.accepted:
            raise ValueError(
                "MCD64A1 文件配对校验失败："
                + pair_result.message
            )

        regions = (
            self.database.list_regions()
        )

        if not regions:
            raise RuntimeError(
                "尚未导入行政区边界，"
                "无法执行 MCD64A1 正式空间落区。"
            )

        region_index = RegionIndex(
            regions
        )

        run_id = (
            self.database.start_import(
                "burned_pixels_tif",
                str(
                    burn_path.resolve()
                ),
                metadata={
                    "task_id": task_id,
                    "burn_file_id": (
                        int(burn_file_id)
                    ),
                    "qa_file_id": (
                        int(qa_file_id)
                    ),
                    "qa_policy": (
                        qa_policy
                    ),
                    "mode": (
                        "task_mcd64_processing"
                    ),
                },
                task_id=task_id,
                input_file_id=(
                    int(burn_file_id)
                ),
            )
        )

        try:
            rows, extraction = (
                extract_mcd64_burned_pixels(
                    burn_path,
                    qa_path=qa_path,
                    region_index=(
                        region_index
                    ),
                    qa_policy=(
                        qa_policy
                    ),
                )
            )

            stored = (
                self.repository
                .store_rows(
                    rows,
                    import_run_id=run_id,
                )
            )

            run_pixels = (
                self.repository
                .list_run_pixels(
                    run_id
                )
            )

            run_area_km2 = sum(
                float(
                    row[
                        "cell_area_km2"
                    ]
                )
                for row
                in run_pixels
            )

            report = {
                "task_id": task_id,
                "run_id": run_id,

                "burn_file_id": (
                    int(burn_file_id)
                ),

                "qa_file_id": (
                    int(qa_file_id)
                ),

                "burn_filename": (
                    burn_record[
                        "original_filename"
                    ]
                ),

                "qa_filename": (
                    qa_record[
                        "original_filename"
                    ]
                ),

                "qa_policy": qa_policy,

                "year": (
                    burn_product_key[0]
                ),

                "month_start_doy": (
                    burn_product_key[1]
                ),

                **extraction,

                "storage_input_pixels": (
                    stored.input_rows
                ),

                "new_burned_pixels": (
                    stored.inserted_pixels
                ),

                "existing_burned_pixels": (
                    stored.existing_pixels
                ),

                "run_memberships_added": (
                    stored
                    .run_memberships_added
                ),

                "run_memberships_existing": (
                    stored
                    .run_memberships_existing
                ),

                # 本次运行真正关联的有效像元。
                "run_burned_pixel_count": (
                    len(run_pixels)
                ),

                # 不从全局 burned_pixels 表求和。
                "run_burned_area_km2": (
                    round(
                        run_area_km2,
                        6,
                    )
                ),
            }

            self.database.finish_import(
                run_id,
                input_count=(
                    extraction[
                        "positive_burn_date_pixels"
                    ]
                ),
                stored_count=(
                    len(run_pixels)
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
        qa_policy: str = "standard",
    ) -> dict[str, Any]:
        """处理任务中全部有效 MCD64A1 月度配对。"""

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
            "mcd64_only",
            "combined",
        }:
            raise ValueError(
                "当前任务分析范围"
                "不包含 MCD64A1。"
            )

        pairs = self._find_valid_pairs(
            task_id
        )

        if not pairs:
            raise ValueError(
                "当前任务没有可用于正式处理的"
                " MCD64A1 Burn Date / QA 有效配对。"
            )

        reports: list[
            dict[str, Any]
        ] = []

        for (
            burn,
            qa,
        ) in pairs:
            reports.append(
                self.process_pair(
                    task_id=task_id,
                    burn_file_id=int(
                        burn["id"]
                    ),
                    qa_file_id=int(
                        qa["id"]
                    ),
                    qa_policy=qa_policy,
                )
            )

        return {
            "task_id": task_id,
            "qa_policy": qa_policy,

            "processed_pairs": (
                len(reports)
            ),

            "reports": reports,

            "new_burned_pixels": sum(
                item[
                    "new_burned_pixels"
                ]
                for item in reports
            ),

            "existing_burned_pixels": sum(
                item[
                    "existing_burned_pixels"
                ]
                for item in reports
            ),

            "run_burned_pixel_count": sum(
                item[
                    "run_burned_pixel_count"
                ]
                for item in reports
            ),

            "run_burned_area_km2": round(
                sum(
                    item[
                        "run_burned_area_km2"
                    ]
                    for item in reports
                ),
                6,
            ),
        }