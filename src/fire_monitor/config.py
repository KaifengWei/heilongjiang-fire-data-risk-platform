"""运行配置。敏感信息只从环境变量读取，不写入仓库。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    """返回项目根目录，不依赖当前工作目录。"""
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    runtime_dir: Path
    database_path: Path
    host: str
    port: int


def load_settings(database_path: str | Path | None = None) -> Settings:
    root = project_root()
    runtime = Path(os.environ.get("FIRE_MONITOR_RUNTIME_DIR", root / "data" / "runtime"))
    runtime.mkdir(parents=True, exist_ok=True)
    db_path = Path(database_path) if database_path else runtime / "fire_monitor.sqlite"
    return Settings(
        project_dir=root,
        runtime_dir=runtime,
        database_path=db_path,
        host=os.environ.get("FIRE_MONITOR_HOST", "127.0.0.1"),
        port=int(os.environ.get("FIRE_MONITOR_PORT", "5060")),
    )
