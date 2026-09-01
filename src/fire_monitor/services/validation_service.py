"""分析任务输入文件接收与基础校验服务。"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from fire_monitor.core.file_validation import (
    SUPPORTED_FILE_ROLES,
    ValidationResult,
    validate_input_file,
)
from fire_monitor.storage.database import Database


class ValidationService:
    """负责保存、校验并登记任务输入文件。"""

    def __init__(
        self,
        database: Database,
        *,
        uploads_root: str | Path,
    ):
        self.database = database
        self.uploads_root = Path(
            uploads_root
        )

        self.database.initialize()

        self.uploads_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def sha256_file(
        path: str | Path,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> str:
        """以流式读取方式计算文件 SHA256。"""

        digest = hashlib.sha256()

        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    @staticmethod
    def _build_stored_name(
        *,
        source: Path,
        file_role: str,
        sha256: str,
        validation: ValidationResult,
    ) -> str:
        """生成内部存储文件名。

        FIRMS 文件使用角色 + SHA256 前缀。

        MCD64A1 文件在内部名称中保留 AYYYYDDD，
        以便后续仍可识别产品月份并进行 Burn Date / QA 配对。
        """

        suffix = source.suffix.lower()

        if file_role in {
            "mcd64_burn_date",
            "mcd64_qa",
        }:
            year = validation.metadata.get(
                "year"
            )

            doy = validation.metadata.get(
                "month_start_doy"
            )

            if year is not None and doy is not None:
                product_token = (
                    f"A{int(year):04d}"
                    f"{int(doy):03d}"
                )

                return (
                    f"{file_role}_"
                    f"{product_token}_"
                    f"{sha256[:12]}"
                    f"{suffix}"
                )

        return (
            f"{file_role}_"
            f"{sha256[:12]}"
            f"{suffix}"
        )

    def receive_local_file(
        self,
        *,
        task_id: str,
        source_path: str | Path,
        file_role: str,
        original_filename: str | None = None,
        source_agency: str | None = None,
        product_name: str | None = None,
        product_version: str | None = None,
        processing_class: str | None = None,
    ) -> dict[str, Any]:
        """接收一个已经存在于本机的输入文件。

        当前方法完成：
        1. 文件存在性检查；
        2. SHA256 计算；
        3. 输入合同校验；
        4. 任务目录隔离存储；
        5. 复制完整性检查；
        6. input_files 数据库登记。

        网页上传功能后续将复用相同业务逻辑。
        """

        if file_role not in SUPPORTED_FILE_ROLES:
            raise ValueError(
                f"不支持的文件角色：{file_role}"
            )

        task = self.database.get_analysis_task(
            task_id
        )

        if task is None:
            raise KeyError(
                f"分析任务不存在：{task_id}"
            )

        source = Path(source_path)

        if not source.is_file():
            raise FileNotFoundError(
                f"输入文件不存在：{source}"
            )

        sha256 = self.sha256_file(
            source
        )

        # 同一任务、同一角色、同一文件内容
        # 不重复登记。
        existing_files = (
            self.database.list_input_files(
                task_id
            )
        )

        for item in existing_files:
            if (
                item["file_role"] == file_role
                and item["sha256"] == sha256
            ):
                return item

        # 在复制之前使用用户原始文件进行校验。
        #
        # 这一点对 MCD64A1 很重要，因为产品日期
        # AYYYYDDD 来源于原始文件名。
        validation = validate_input_file(
            source,
            file_role=file_role,
        )

        task_directory = (
            self.uploads_root / task_id
        )

        task_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        stored_name = self._build_stored_name(
            source=source,
            file_role=file_role,
            sha256=sha256,
            validation=validation,
        )

        destination = (
            task_directory / stored_name
        )

        if not destination.exists():
            shutil.copy2(
                source,
                destination,
            )

        # 复制完成后再次计算 SHA256，
        # 防止复制过程产生内容变化。
        stored_sha256 = self.sha256_file(
            destination
        )

        if stored_sha256 != sha256:
            try:
                destination.unlink()
            except OSError:
                pass

            raise IOError(
                "输入文件复制后 SHA256 不一致，"
                "文件未登记。"
            )

        file_id = (
            self.database.register_input_file(
                task_id=task_id,
                file_role=file_role,
                original_filename=(
                        original_filename
                        or source.name
                ),
                stored_path=str(
                    destination.resolve()
                ),
                sha256=sha256,
                size_bytes=(
                    destination.stat().st_size
                ),
                source_agency=source_agency,
                product_name=product_name,
                product_version=product_version,
                processing_class=processing_class,
                crs=validation.metadata.get(
                    "crs"
                ),
                validation_status=(
                    validation.status
                ),
                validation_message=(
                    validation.message
                ),
                metadata={
                    "validation": (
                        validation.metadata
                    ),
                },
            )
        )

        records = (
            self.database.list_input_files(
                task_id
            )
        )

        for record in records:
            if record["id"] == file_id:
                return record

        raise RuntimeError(
            "输入文件登记完成后无法重新读取。"
        )