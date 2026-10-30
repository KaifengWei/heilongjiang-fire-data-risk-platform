"""Persistent local crop-calendar rule store (not a national agronomic default)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fire_monitor.services.agricultural_relevance_service import validate_calendar_rules

MAX_BYTES = 64 * 1024


class CropCalendarStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_rules(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        data = self.path.read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError("农事时段文件超过64 KB上限。")
        payload = json.loads(data.decode("utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("农事规则文件格式不正确（需要schema_version=1）。")
        return validate_calendar_rules(payload.get("rules"))

    def import_json(self, data: bytes) -> int:
        if not data or len(data) > MAX_BYTES:
            raise ValueError("农事时段文件为空或超过64 KB。")
        try:
            payload: Any = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("农事时段文件必须为UTF-8 JSON。") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("农事规则必须是schema_version=1的JSON对象。")
        rules = validate_calendar_rules(payload.get("rules"))
        if not rules:
            raise ValueError("请提供至少一条有来源的地区农事规则。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalized = json.dumps(
            {"schema_version": 1, "rules": rules},
            ensure_ascii=False, indent=2,
        ).encode("utf-8")
        with NamedTemporaryFile(
            mode="wb", dir=self.path.parent,
            prefix=".crop-calendar-", suffix=".tmp", delete=False
        ) as handle:
            tmp_name = handle.name
            handle.write(normalized)
        try:
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return len(rules)
