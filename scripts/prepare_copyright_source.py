"""Build traceable preliminary source-code pages for software registration.

No files are modified in the original repository. Runtime Python, JavaScript,
CSS and HTML are included; tests, generated assets and build utilities are
catalogued separately rather than represented as user-facing application code.

The 60-page DOCX is a *layout candidate*, NOT a registered or verified final
submission. Check page count, physical line wrapping, name/version and actual
Windows GUI acceptance before submitting.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Iterable


SOFTWARE_NAME = "农业秸秆焚烧区域火点检测与分析平台"
LINE_PER_PAGE = 50
PAGES_PER_SIDE = 30
SUPPORTED_SUFFIXES = {".py", ".js", ".css", ".html"}
FRONTEND_SUFFIXES = {".js", ".css", ".html"}


@dataclass(frozen=True)
class SourceLine:
    path: str
    original_line: int
    text: str


def discover_program_sources(project_root: Path) -> list[Path]:
    """Only authored runtime modules are included, in stable grouping order."""
    root = Path(project_root)
    result: list[Path] = []
    for entry in ("main.py", "desktop.py"):
        path = root / entry
        if path.is_file():
            result.append(path)
    for relative, extensions in (
        ("src/fire_monitor", {".py"}),
        ("static", {".js", ".css"}),
        ("templates", {".html"}),
    ):
        base = root / relative
        if not base.is_dir():
            continue
        files = (
            path for path in base.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions
            and not path.name.endswith(".min.js")
            and "__pycache__" not in path.parts
            and "node_modules" not in path.parts
        )
        result.extend(sorted(files, key=lambda path: path.relative_to(root).as_posix()))
    return result


def read_sources(
    root: Path,
    paths: Iterable[Path],
) -> tuple[list[dict], list[SourceLine]]:
    inventory: list[dict] = []
    effective: list[SourceLine] = []
    for path in paths:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        original = text.splitlines()
        relative = path.relative_to(root).as_posix()
        nonblank = 0
        for index, line in enumerate(original, 1):
            if not line.strip():
                continue
            effective.append(SourceLine(relative, index, line))
            nonblank += 1
        inventory.append({
            "file": relative,
            "language": path.suffix.lower().lstrip("."),
            "original_lines": len(original),
            "nonblank_lines": nonblank,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return inventory, effective


def candidate_regions(
    lines: list[SourceLine],
    *,
    per_page: int = LINE_PER_PAGE,
    pages_each: int = PAGES_PER_SIDE,
) -> list[tuple[str, int, list[SourceLine]]]:
    if per_page < 1 or pages_each < 1:
        raise ValueError("per_page and pages_each must be positive")
    portion = pages_each * per_page
    if len(lines) > 2 * portion:
        front = lines[:portion]
        back = lines[-portion:]
        segments = [("前30页", front), ("后30页", back)]
    else:
        segments = [("全部源程序", lines)]
    result: list[tuple[str, int, list[SourceLine]]] = []
    page_no = 0
    for region, selection in segments:
        for offset in range(0, len(selection), per_page):
            page_no += 1
            result.append((region, page_no, selection[offset: offset + per_page]))
    return result


def _write_csv(path: Path, headers: list[str], data: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)


def _git_commit(project_root: Path) -> str:
    try:
        command = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root, check=True,
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired):
        return "未能读取（候选材料未锁定版本）"
    return command.stdout.strip() or "未能读取（候选材料未锁定版本）"


def _write_preliminary_docx(
    output: Path,
    pages: list[tuple[str, int, list[SourceLine]]],
    software_version: str,
) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.55)
    section.right_margin = Cm(1.25)
    section.header_distance = Cm(.7)
    section.footer_distance = Cm(.65)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    header_run = header.add_run(
        SOFTWARE_NAME + "  " + software_version + "  源程序（候选稿）"
    )
    header_run.font.size = Pt(8)
    header_run.font.name = "SimSun"

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("第 ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    footer.add_run(" 页（正式页数需在 Word 中复核）")

    style = doc.styles["Normal"]
    style.font.name = "Consolas"
    style.font.size = Pt(7.3)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = Pt(9.7)

    for page_index, (_, _, rows) in enumerate(pages):
        if page_index:
            doc.add_page_break()
        for item in rows:
            paragraph = doc.add_paragraph(style="Normal")
            # Preserve the exact non-empty source text; only empty lines are
            # suppressed so each candidate page contains 50 effective lines.
            paragraph.add_run(item.text)

    doc.core_properties.title = SOFTWARE_NAME + " 源程序候选稿"
    doc.core_properties.subject = "来源可追溯的源码前后30页排版预览"
    doc.save(output)


def prepare_source_material(
    project_root: Path,
    output_dir: Path,
    *,
    software_version: str = "V1.0",
    include_docx: bool = True,
    per_page: int = LINE_PER_PAGE,
    pages_each: int = PAGES_PER_SIDE,
) -> dict:
    root = Path(project_root).resolve()
    output = Path(output_dir).resolve()
    if not (root / "src" / "fire_monitor").is_dir():
        raise ValueError("Project root must contain src/fire_monitor")
    # Prevent reading generated output as a candidate source on reruns.
    paths = discover_program_sources(root)
    if not paths:
        raise ValueError("No program source files found")
    inventory, lines = read_sources(root, paths)
    if not lines:
        raise ValueError("All source files contain no source statements")
    pages = candidate_regions(lines, per_page=per_page, pages_each=pages_each)
    output.mkdir(parents=True, exist_ok=True)

    _write_csv(
        output / "源文件清单.csv",
        ["file", "language", "original_lines", "nonblank_lines", "sha256"],
        inventory,
    )
    records = []
    page_index = []
    long_lines = 0
    for region, number, rows in pages:
        start = rows[0]
        end = rows[-1]
        page_index.append({
            "page": number,
            "section": region,
            "source_lines": len(rows),
            "start_file": start.path,
            "start_original_line": start.original_line,
            "end_file": end.path,
            "end_original_line": end.original_line,
        })
        for order, item in enumerate(rows, 1):
            records.append({
                "printed_page": number,
                "printed_line": order,
                "section": region,
                "source_file": item.path,
                "source_original_line": item.original_line,
                "source_text": item.text,
            })
            if len(item.text.expandtabs(4)) > 120:
                long_lines += 1
    _write_csv(
        output / "源码逐行溯源.csv",
        ["printed_page", "printed_line", "section", "source_file",
         "source_original_line", "source_text"],
        records,
    )
    _write_csv(
        output / "每页源码来源.csv",
        ["page", "section", "source_lines", "start_file",
         "start_original_line", "end_file", "end_original_line"],
        page_index,
    )

    parts = {"前30页": [], "后30页": [], "全部源程序": []}
    for region, _, rows in pages:
        parts[region].extend(row.text for row in rows)
    if parts["全部源程序"]:
        (output / "全部源程序候选.txt").write_text(
            "\n".join(parts["全部源程序"]) + "\n", encoding="utf-8",
        )
    else:
        (output / "前30页源码候选.txt").write_text(
            "\n".join(parts["前30页"]) + "\n", encoding="utf-8",
        )
        (output / "后30页源码候选.txt").write_text(
            "\n".join(parts["后30页"]) + "\n", encoding="utf-8",
        )

    if include_docx:
        _write_preliminary_docx(
            output / "源程序前后30页_待排版核验.docx",
            pages,
            software_version,
        )

    summary = {
        "product": SOFTWARE_NAME,
        "software_version_candidate": software_version,
        "source_commit": _git_commit(root),
        "file_count": len(inventory),
        "original_source_lines": sum(x["original_lines"] for x in inventory),
        "nonblank_source_lines": len(lines),
        "by_type": {
            suffix: {
                "files": sum(x["language"] == suffix for x in inventory),
                "nonblank_lines": sum(
                    x["nonblank_lines"] for x in inventory
                    if x["language"] == suffix
                ),
            }
            for suffix in ("py", "js", "css", "html")
        },
        "candidate_pages": len(pages),
        "lines_per_candidate_page": per_page,
        "pages_per_side": pages_each,
        "printed_nonblank_lines": len(records),
        "long_source_lines_over_120_characters": long_lines,
        "may_wrap_in_word": bool(long_lines),
        "is_final_submission": False,
        "windows_gui_accepted": False,
        "note": (
            "This is a reproducible preliminary source manuscript. "
            "Blank original source lines are omitted, all remaining source "
            "characters and file order are retained. Review long-line "
            "wrapping, actual Word page count, copyright ownership, "
            "software title/version and GUI acceptance before submission."
        ),
    }
    (output / "源码整理统计.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare traceable code pages for copyright review.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=Path("release") / "softcopyright_draft")
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--skip-docx", action="store_true")
    options = parser.parse_args()
    summary = prepare_source_material(
        options.root, options.out,
        software_version=options.version,
        include_docx=not options.skip_docx,
    )
    print("Source files:", summary["file_count"])
    print("Original lines:", summary["original_source_lines"])
    print("Nonblank code lines:", summary["nonblank_source_lines"])
    print("Candidate pages:", summary["candidate_pages"])
    print("Long lines requiring Word layout review:",
          summary["long_source_lines_over_120_characters"])
    print("Candidate only; Windows GUI and final Word pagination NOT approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
