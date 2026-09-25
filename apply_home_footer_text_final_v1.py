#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CSS = ROOT / "static" / "product.css"
BACKUP = (
    ROOT
    / "data"
    / "runtime"
    / "home_footer_text_final_v1_backup"
)

CSS_OVERRIDE = r'''
/* =========================================================
   HOME FOOTER TEXT FINAL V1
   Final typography adjustment for homepage capability cards.
   ========================================================= */

.home-capability-index {
  font-size: 12px !important;
  font-weight: 800 !important;
  letter-spacing: .12em !important;
}

.home-capabilities h2 {
  font-size: 17px !important;
  line-height: 1.45 !important;
  font-weight: 700 !important;
  margin-bottom: 10px !important;
}

.home-capabilities p {
  font-size: 14px !important;
  line-height: 1.8 !important;
}

.home-capabilities article {
  padding-top: 32px !important;
  padding-bottom: 32px !important;
}
'''


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(
        path.name + ".tmp_home_footer_text_final_v1"
    )
    tmp.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def run_checked(cmd: list[str], label: str) -> None:
    print(f"\n==> {label}")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            f"{label}失败，退出码：{result.returncode}"
        )


def main() -> int:
    if not CSS.is_file():
        raise FileNotFoundError(
            f"未找到：{CSS}"
        )

    if BACKUP.exists():
        shutil.rmtree(BACKUP)

    backup_file = (
        BACKUP
        / CSS.relative_to(ROOT)
    )
    backup_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        CSS,
        backup_file,
    )

    try:
        css = CSS.read_text(
            encoding="utf-8"
        )

        marker = (
            "/* =========================================================\n"
            "   HOME FOOTER TEXT FINAL V1"
        )

        if marker in css:
            css = css.split(
                marker,
                1,
            )[0].rstrip()

        atomic_write(
            CSS,
            css
            + "\n\n"
            + CSS_OVERRIDE.strip()
            + "\n",
        )

        run_checked(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
            "完整 pytest",
        )

    except Exception:
        shutil.copy2(
            backup_file,
            CSS,
        )
        print(
            "\n修改或验证失败，已自动恢复 product.css。",
            file=sys.stderr,
        )
        raise

    print("\n========================================")
    print("首页底部文字最终调整已完成")
    print("========================================")
    print("编号：11px -> 12px")
    print("标题：15px -> 17px")
    print("正文：12px -> 14px")
    print("布局、颜色、功能均未修改")
    print()
    print("确认后即可重新构建 EXE 并封存当前版本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
