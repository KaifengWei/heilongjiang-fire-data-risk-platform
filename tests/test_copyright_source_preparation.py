"""A software-copyright source preview is deterministic and source-traceable."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.prepare_copyright_source import (
    candidate_regions,
    discover_program_sources,
    prepare_source_material,
    read_sources,
)


def _runtime_project(root: Path):
    (root / "src" / "fire_monitor" / "services").mkdir(parents=True)
    (root / "static").mkdir()
    (root / "templates").mkdir()
    (root / "tests").mkdir()
    (root / "scripts").mkdir()
    (root / "main.py").write_text("print('program')\n", encoding="utf-8")
    (root / "desktop.py").write_text("start()\n", encoding="utf-8")
    (root / "src" / "fire_monitor" / "__init__.py").write_text(
        "# runtime package\n", encoding="utf-8"
    )
    (root / "src" / "fire_monitor" / "services" / "app.py").write_text(
        "def run():\n\n    return 1\n", encoding="utf-8"
    )
    (root / "static" / "app.js").write_text(
        "const value = 42;\n", encoding="utf-8"
    )
    (root / "static" / "main.css").write_text(
        ".card {color: red;}\n", encoding="utf-8"
    )
    (root / "templates" / "home.html").write_text(
        "<main>real template</main>\n", encoding="utf-8"
    )
    (root / "tests" / "test_app.py").write_text(
        "assert True\n", encoding="utf-8"
    )
    (root / "scripts" / "build.py").write_text(
        "print('build helper')\n", encoding="utf-8"
    )


def test_sources_include_python_and_frontend_without_tests_or_build_scripts(tmp_path):
    _runtime_project(tmp_path)
    files = discover_program_sources(tmp_path)
    names = [p.relative_to(tmp_path).as_posix() for p in files]
    assert names == [
        "main.py",
        "desktop.py",
        "src/fire_monitor/__init__.py",
        "src/fire_monitor/services/app.py",
        "static/app.js",
        "static/main.css",
        "templates/home.html",
    ]
    inventory, lines = read_sources(tmp_path, files)
    assert sum(x["nonblank_lines"] for x in inventory) == len(lines)
    assert all("tests/" not in row.path for row in lines)
    assert all("scripts/" not in row.path for row in lines)
    assert all(x["sha256"] for x in inventory)
    assert [row.text for row in lines][:2] == ["print('program')", "start()"]


def test_pages_use_first_last_continuous_source_without_overlap_or_filler():
    from scripts.prepare_copyright_source import SourceLine

    lines = [SourceLine("src/fire_monitor/huge.py", i, f"CODE_{i}")
             for i in range(1, 3251)]
    pages = candidate_regions(lines)
    assert len(pages) == 60
    assert pages[0][0] == "前30页"
    assert pages[0][1] == 1
    assert pages[0][2][0].text == "CODE_1"
    assert pages[29][2][-1].text == "CODE_1500"
    assert pages[30][0] == "后30页"
    assert pages[30][2][0].text == "CODE_1751"
    assert pages[-1][2][-1].text == "CODE_3250"
    assert all(len(page[2]) == 50 for page in pages)
    assert len({row.text for _, _, rows in pages for row in rows}) == 3000


def test_smaller_program_is_not_repeated_to_fill_60_pages():
    from scripts.prepare_copyright_source import SourceLine

    lines = [SourceLine("src/fire_monitor/mod.py", i, "x = 1")
             for i in range(1, 78)]
    pages = candidate_regions(lines)
    assert len(pages) == 2
    assert pages[0][0] == pages[1][0] == "全部源程序"
    assert len(pages[0][2]) == 50
    assert len(pages[1][2]) == 27


def test_cli_outputs_traceable_inventory_and_nonfinal_status(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _runtime_project(project)
    output = tmp_path / "copyright-preview"
    summary = prepare_source_material(
        project, output, include_docx=False,
    )
    assert summary["file_count"] == 7
    assert summary["nonblank_source_lines"] == 8
    assert summary["candidate_pages"] == 1
    assert not summary["is_final_submission"]
    assert not summary["windows_gui_accepted"]
    assert "py" in summary["by_type"]
    assert "js" in summary["by_type"]
    assert "css" in summary["by_type"]
    assert "html" in summary["by_type"]

    line_rows = list(csv.DictReader(
        (output / "源码逐行溯源.csv").open(encoding="utf-8-sig")
    ))
    assert len(line_rows) == 8
    assert line_rows[0]["source_file"] == "main.py"
    assert line_rows[0]["source_original_line"] == "1"
    assert line_rows[0]["source_text"] == "print('program')"
    assert line_rows[-1]["source_file"] == "templates/home.html"
    assert (output / "全部源程序候选.txt").is_file()
    assert not (output / "前30页源码候选.txt").exists()

    saved = json.loads((output / "源码整理统计.json").read_text(encoding="utf-8"))
    assert saved["file_count"] == summary["file_count"]
    assert saved["candidate_pages"] == 1


def test_real_repository_program_sources_have_no_test_fixtures_or_assets():
    root = Path(__file__).resolve().parents[1]
    names = [
        path.relative_to(root).as_posix()
        for path in discover_program_sources(root)
    ]
    assert "main.py" in names
    assert "desktop.py" in names
    assert "src/fire_monitor/app.py" in names
    assert "src/fire_monitor/services/report_docx_service.py" in names
    assert "static/weather_context.js" in names
    assert "static/result_console.css" in names
    assert "templates/task_detail.html" in names
    assert not any(path.startswith(("tests/", "scripts/")) for path in names)
    assert not any(path.endswith((".csv", ".json", ".webp")) for path in names)



def test_docx_candidate_contains_exact_selected_code_lines(tmp_path):
    from docx import Document

    project = tmp_path / "project"
    project.mkdir()
    _runtime_project(project)
    out = tmp_path / "draft"
    summary = prepare_source_material(
        project, out, include_docx=True,
    )
    manuscript = out / "源程序前后30页_待排版核验.docx"
    assert manuscript.is_file()
    doc = Document(manuscript)
    printed = [paragraph.text for paragraph in doc.paragraphs if paragraph.text]
    assert len(printed) == summary["printed_nonblank_lines"]
    assert printed[0] == "print('program')"
    assert printed[-1] == "<main>real template</main>"
    assert summary["is_final_submission"] is False
