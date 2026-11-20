"""Registration drafts reflect current executables and avoid invented facts."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "SOFTWARE_MANUAL_V1_DRAFT.md"
FORM = ROOT / "docs" / "SOFTWARE_REGISTRATION_FORM_DRAFT.md"
PRODUCT = "农业秸秆焚烧区域火点检测与分析平台"


def test_manual_has_real_interface_entry_points_and_complete_workflow():
    manual = MANUAL.read_text(encoding="utf-8")
    home = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    upload = (ROOT / "templates" / "analyze.html").read_text(encoding="utf-8")
    records = (ROOT / "templates" / "tasks.html").read_text(encoding="utf-8")
    result = (ROOT / "templates" / "task_detail.html").read_text(encoding="utf-8")
    desktop = (ROOT / "src" / "fire_monitor" / "desktop.py").read_text(
        encoding="utf-8"
    )

    assert PRODUCT in manual
    assert PRODUCT in desktop
    assert PRODUCT in home
    assert "## 1 简介" in manual
    assert "## 2 产品概述" in manual
    assert "## 3 使用说明" in manual
    assert "## 4 数据管理与结果使用" in manual
    assert "## 5 " not in manual
    assert "开始区域火点分析" in manual and "开始区域火点分析" in upload
    assert "查看 CSV 观测范围" in manual and "查看 CSV 观测范围" in upload
    assert "重命名" in manual and "重命名" in records
    assert "导出分析报告" in manual and "导出分析报告" in result
    assert "观测最多的三个网格" in manual and "观测最多的三个网格" in result
    assert "3.9 导出 Word 图文报告" in manual
    assert "图 3-9" in manual
    assert "【待插入" in manual
    assert "待实机" in manual


def test_application_materials_do_not_reintroduce_old_brand_or_invent_metadata():
    for path in (MANUAL, FORM):
        content = path.read_text(encoding="utf-8")
        assert PRODUCT in content
        assert "黑龙江" not in content
        assert "WebView2" not in content
        assert "PySide6" not in content
        assert "等待确认" in content or "待确认" in content or "待登记" in content
        assert "火灾发生概率" not in content or "不输出火灾发生概率" in content


def test_registration_form_stays_within_user_required_character_limits():
    content = FORM.read_text(encoding="utf-8")
    main = re.search(
        r"^## 主要功能（不超过 500 字，候选）\s*\n(.*?)\n## 技术特点",
        content, flags=re.M | re.S,
    )
    technical = re.search(
        r"^## 技术特点（不超过 100 字，候选）\s*\n(.*?)\n## 主要用途",
        content, flags=re.M | re.S,
    )
    assert main and technical
    main_text = main.group(1).strip()
    technical_text = technical.group(1).strip()
    assert len(main_text) <= 500, len(main_text)
    assert len(technical_text) <= 100, len(technical_text)
    for required in ("FIRMS", "GeoJSON", "MCD12Q1", "NASA POWER", "NOAA GFS", "Word"):
        assert required in main_text
    assert "Windows" in technical_text
    assert "pywebview" in technical_text
    assert "Flask" in technical_text


def test_draft_notes_do_not_claim_gui_signoff():
    manual = MANUAL.read_text(encoding="utf-8")
    form = FORM.read_text(encoding="utf-8")
    handoff = (ROOT / "docs" / "SOFTWARE_COPYRIGHT_HANDOFF.md").read_text(
        encoding="utf-8"
    )
    assert "待实机验收" in manual
    assert "待确认" in form
    assert "SOFTWARE_MANUAL_V1_DRAFT.md" in handoff
    assert "SOFTWARE_REGISTRATION_FORM_DRAFT.md" in handoff



def test_architecture_scope_and_material_index_use_current_product_name():
    for doc in (
        ROOT / "docs" / "00_项目范围与功能边界.md",
        ROOT / "docs" / "01_系统架构设计.md",
    ):
        text = doc.read_text(encoding="utf-8")
        assert PRODUCT in text
        assert "黑龙江" not in text
        assert "SOFTWARE_MANUAL_V1_DRAFT.md" in text
        assert "SOFTWARE_REGISTRATION_FORM_DRAFT.md" in text

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/SOFTWARE_MANUAL_V1_DRAFT.md" in readme
    assert "docs/SOFTWARE_REGISTRATION_FORM_DRAFT.md" in readme
