"""User-facing Word report aligned with platform assessment outputs."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


BLACK = RGBColor(0, 0, 0)
BORDER = "D9D9D9"
SHADE = "F3F3F3"
BAR_FILL = "8FB5CC"
BAR_EMPTY = "EDF3F6"


def _set_run_font(run, size: float = 11, bold: bool = False) -> None:
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "宋体")
    rfonts.set(qn("w:cs"), "Times New Roman")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = BLACK


def _paragraph(doc: Document, pieces: list[tuple[str, bool]], *, size: float = 11, after: float = 8, align=None) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.widow_control = True
    if align is not None:
        p.alignment = align
    for text, bold in pieces:
        run = p.add_run(str(text))
        _set_run_font(run, size=size, bold=bold)


def _heading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(7)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.keep_together = True
    run = p.add_run(text)
    _set_run_font(run, size=13.5, bold=True)


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_border(cell, color: str = BORDER) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def _keep_row_intact(row, *, repeat_header: bool = False) -> None:
    """Repeat column headers and keep each action row on one Word page."""
    props = row._tr.get_or_add_trPr()
    if props.find(qn("w:cantSplit")) is None:
        props.append(OxmlElement("w:cantSplit"))
    if repeat_header and props.find(qn("w:tblHeader")) is None:
        props.append(OxmlElement("w:tblHeader"))


def _summary_table(doc: Document, analysis_summary: dict[str, Any], historical_baseline: dict[str, Any], firms_intelligence: dict[str, Any]) -> None:
    summary = firms_intelligence.get("summary") or {}
    if analysis_summary.get("area_mode") == "coordinates_only":
        # Use the front-page space for decision-relevant facts. A declared
        # region has no validated historical comparator or city ranking.
        rows = [
            ("有效火点观测", _fmt_int(analysis_summary.get("active_fire_count"))),
            ("观测日期范围", str(analysis_summary.get("period") or "—")),
            ("峰值日期", (
                f"{summary['peak_date']}（{_fmt_int(summary.get('peak_count'))} 条）"
                if summary.get("peak_date") else "—"
            )),
            ("有火点日期", f"{_fmt_int(summary.get('active_days'))} 天"),
        ]
    else:
        priority = historical_baseline.get("priority_regions", []) if historical_baseline else []
        priority_names = "、".join(str(x.get("region_name")) for x in priority[:3] if x.get("region_name")) or str(analysis_summary.get("main_region") or "—")
        history_status = str(historical_baseline.get("province_status") or "暂无历史同期判断") if historical_baseline and historical_baseline.get("available") else "暂无历史同期判断"
        rows = [
            ("历史同期判断", history_status),
            ("有效火点观测", _fmt_int(analysis_summary.get("active_fire_count"))),
            ("火点最集中区域", str(analysis_summary.get("main_region") or "—")),
            ("峰值日期", (
                f"{summary['peak_date']}（{_fmt_int(summary.get('peak_count'))} 条）"
                if summary.get("peak_date") else "—"
            )),
            ("活跃日期", f"{_fmt_int(summary.get('active_days'))} / {_fmt_int(summary.get('span_days'))}"),
            ("重点核查地区", priority_names),
        ]
    table = doc.add_table(rows=len(rows) // 2, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    index = 0
    for row in table.rows:
        _keep_row_intact(row)
        for col in (0, 2):
            label, value = rows[index]
            c1, c2 = row.cells[col], row.cells[col + 1]
            for c in (c1, c2):
                c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                _set_cell_border(c)
            _shade(c1, SHADE)
            p = c1.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            _set_run_font(p.add_run(label), size=9.75, bold=True)
            p = c2.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            _set_run_font(p.add_run(value), size=10.25, bold=label in {
                "历史同期判断", "火点最集中区域", "有效火点观测",
                "峰值日期", "重点核查地区",
            })
            index += 1


def _top_regions(regions: list[dict[str, Any]], topn: int = 5) -> list[dict[str, Any]]:
    return sorted(regions, key=lambda x: int(x.get("observation_count") or 0), reverse=True)[:topn]


def _bar_row(cell, ratio: float, segments: int = 10) -> None:
    ratio = min(1.0, max(0.0, ratio))
    filled = max(1 if ratio > 0 else 0, round(ratio * segments))
    nested = cell.add_table(rows=1, cols=segments)
    nested.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, segment in enumerate(nested.rows[0].cells):
        _shade(segment, BAR_FILL if index < filled else BAR_EMPTY)
        _set_cell_border(segment, "FFFFFF")
        segment.width = Cm(0.55)
        p = segment.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(" ")
        _set_run_font(r, size=4)


def _visual_bar_table(doc: Document, rows: list[tuple[str, int]], caption: str) -> None:
    if not rows:
        return
    max_value = max(value for _, value in rows) or 1
    table = doc.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _keep_row_intact(table.rows[0], repeat_header=True)
    for cell, header in zip(table.rows[0].cells, ("项目", "数量", "相对强度")):
        _shade(cell, SHADE)
        _set_cell_border(cell)
        p = cell.paragraphs[0]
        r = p.add_run(header)
        _set_run_font(r, size=10, bold=True)
    for label, value in rows:
        row = table.add_row()
        _keep_row_intact(row)
        cells = row.cells
        for c in cells:
            _set_cell_border(c)
        p = cells[0].paragraphs[0]
        r = p.add_run(label)
        _set_run_font(r, size=10, bold=True)
        p = cells[1].paragraphs[0]
        r = p.add_run(_fmt_int(value))
        _set_run_font(r, size=10)
        _bar_row(cells[2], value / max_value)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(caption)
    _set_run_font(r, size=9.5)


def _hotspot_next_action(item: dict[str, Any]) -> str:
    """Turn observation evidence into a review task, without a risk score."""
    peak_date = str(item.get("peak_date") or "").strip()
    active_days = int(item.get("active_days") or 0)
    if peak_date and active_days >= 2:
        steps = [
            f"对照 {peak_date} 的卫星影像，"
            f"再复核其余 {active_days - 1} 个有记录日期的点位分布"
        ]
    elif peak_date:
        steps = [f"先核对 {peak_date} 对应时段的卫星影像及周边热源"]
    else:
        steps = ["先核对本次 FIRMS 观测时间并查阅对应卫星影像"]
    if int(item.get("cropland_background_count") or 0) > 0:
        steps.append("结合耕地分布核实对应田块，并核对当期收获和秸秆处理记录")
    elif int(item.get("known_surface_count") or 0) > 0:
        steps.append("结合已识别地表类型核查非农热源或其他热异常成因")
    else:
        steps.append("以实测点坐标定位高分辨率影像，先确定地表类型和邻近固定热源")
    return "；".join(steps) + "。"


def _spatial_hotspot_table(doc: Document, rows: list[dict[str, Any]]) -> None:
    """A short review plan: where to look, why, and what to check."""
    if not rows:
        return
    columns = ("地图序号及核查范围", "观测依据", "具体核查事项")
    table = doc.add_table(rows=1, cols=len(columns))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    # The A4 body is 17 cm wide: give the actionable third column
    # roughly half the usable width, instead of equal narrow columns.
    for col, width in zip(table.columns, (Cm(4.3), Cm(4.4), Cm(8.3))):
        col.width = width
    _keep_row_intact(table.rows[0], repeat_header=True)
    for cell, title in zip(table.rows[0].cells, columns):
        _shade(cell, SHADE)
        _set_cell_border(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_run_font(cell.paragraphs[0].add_run(title), size=9.5, bold=True)

    for item in rows:
        west, south, east, north = item["bbox"]
        active_days = int(item.get("active_days") or 0)
        evidence = (
            f"{_fmt_int(item['count'])} 条观测，占 {item['share_percent']:.1f}%；"
            + (f"分布于 {active_days} 个日期" if active_days else "日期待核对")
        )
        if item.get("peak_date"):
            evidence += (
                f"；高值日 {item['peak_date']}"
                f"（{_fmt_int(item.get('peak_count'))} 条）"
            )
        sample = item.get("sample_observation") or {}
        point_text = (
            f"\n实测点 {float(sample['longitude']):.5f}°E，"
            f"{float(sample['latitude']):.5f}°N"
            if "longitude" in sample and "latitude" in sample else ""
        )
        values = (
            f"位置 {int(item['rank'])}\n东经 {west:.2f}°～{east:.2f}°\n"
            f"北纬 {south:.2f}°～{north:.2f}°" + point_text,
            evidence,
            _hotspot_next_action(item),
        )
        row = table.add_row()
        _keep_row_intact(row)
        for cell, value in zip(row.cells, values):
            _set_cell_border(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            _set_run_font(paragraph.add_run(value), size=9.25)


def _overall_paragraph(analysis_summary: dict[str, Any], firms_intelligence: dict[str, Any]) -> list[tuple[str, bool]]:
    total = int(analysis_summary.get("active_fire_count") or 0)
    top = _top_regions(firms_intelligence.get("regions") or [], 3)
    pieces: list[tuple[str, bool]] = [
        ("本次分析覆盖 ", False), (str(analysis_summary.get("period") or "—"), True),
        ("，共识别 ", False), (_fmt_int(total), True),
        (" 条有效主动火点观测。", False),
    ]
    if analysis_summary.get("area_mode") == "coordinates_only":
        return pieces
    pieces += [("涉及 ", False), (_fmt_int(analysis_summary.get("affected_regions")), True),
               (" 个市（地）。", False)]
    if top:
        top3_total = sum(int(row.get("observation_count") or 0) for row in top)
        parts = []
        for row in top:
            count = int(row.get("observation_count") or 0)
            share = count / total * 100 if total else 0.0
            parts.append((str(row.get("region_name") or "—"), count, share))
        pieces += [
            ("从空间分布看，", False), (parts[0][0], True), (" 最为集中，共 ", False), (_fmt_int(parts[0][1]), True),
            (" 条，约占本次统计总量 ", False), (f"{parts[0][2]:.1f}%", True), ("。", False),
        ]
        if len(parts) > 1:
            pieces += [("其次为 ", False), (parts[1][0], True), ("，共 ", False), (_fmt_int(parts[1][1]), True), (" 条。", False)]
        pieces += [("前三个地区合计约占本次有效观测的 ", False), (f"{top3_total / total * 100 if total else 0:.1f}%", True), ("，火点在空间上表现出较明显的集中分布。", False)]
    return pieces


def _time_paragraph(firms_intelligence: dict[str, Any]) -> list[tuple[str, bool]]:
    summary = firms_intelligence.get("summary") or {}
    anomalies = firms_intelligence.get("anomaly_days") or []
    repeated = firms_intelligence.get("repeated_cells") or []
    pieces: list[tuple[str, bool]] = [
        ("从时间变化看，本次任务共有 ", False), (_fmt_int(summary.get("active_days")), True), (" 个活跃日期。", False),
    ]
    if summary.get("peak_date"):
        pieces += [(str(summary.get("peak_date")), True), (" 是本次最突出的高值日，当天共记录 ", False), (_fmt_int(summary.get("peak_count")), True), (" 条火点观测。", False)]
    if anomalies:
        pieces += [("软件同时将 ", False), (str(anomalies[0].get("date") or "该日期"), True), (" 识别为火点明显增多日期，适合单独回到地图查看其空间分布。", False)]
    if repeated:
        row = repeated[0]
        pieces += [("持续性方面，", False), (str(row.get("region_name") or "部分区域"), True), (" 等地存在跨多个日期重复出现的活跃位置，其中最突出的约 ", False), (f"{row.get('grid_km', 5):g} km", True), (" 网格累计覆盖 ", False), (_fmt_int(row.get("active_days")), True), (" 个活跃日期。", False)]
    return pieces


def _assessment_paragraph(historical_baseline: dict[str, Any], firms_intelligence: dict[str, Any], priority_land_cover: dict[str, Any] | None) -> list[tuple[str, bool]]:
    pieces: list[tuple[str, bool]] = []
    if historical_baseline and historical_baseline.get("available"):
        status = str(historical_baseline.get("province_status") or "—")
        pieces += [("历史同期对比显示，本次火点活动整体处于 ", False), (status, True), (" 水平。", False)]
        priority = historical_baseline.get("priority_regions") or []
        if priority:
            names = "、".join(str(row.get("region_name") or "—") for row in priority[:3])
            pieces += [("平台列出的重点核查地区为 ", False), (names, True), ("。", False)]
            details = []
            for row in priority[:3]:
                name = str(row.get("region_name") or "—")
                attention = str(row.get("attention") or "")
                reasons = "；".join(str(x) for x in (row.get("reasons") or []) if x)
                detail = name
                if attention:
                    detail += f"（{attention}）"
                if reasons:
                    detail += f"：{reasons}"
                details.append(detail)
            if details:
                pieces += [("具体来看，" + "；".join(details) + "。", False)]
        else:
            pieces += [("当前没有单独列出的历史同期重点地区，可按火点数量和高值日期进行常规查看。", False)]
    else:
        pieces += [("当前任务没有形成可用的历史同期判断。", False)]
    if priority_land_cover and priority_land_cover.get("message"):
        pieces += [("地表背景方面，", False), (str(priority_land_cover.get("message")), True), ("。", False)]
    repeated = firms_intelligence.get("repeated_cells") or []
    if repeated:
        pieces += [("同时，", False), (str(repeated[0].get("region_name") or "部分地区"), True), (" 已出现持续活跃位置，适合与重点核查地区一起查看。", False)]
    return pieces


def _land_paragraph(land_cover_context: dict[str, Any]) -> list[tuple[str, bool]] | None:
    if not land_cover_context or not land_cover_context.get("available"):
        return None
    matched = int(land_cover_context.get("matched_observations") or 0)
    total = int(land_cover_context.get("total_observations") or 0)
    pieces: list[tuple[str, bool]] = [
        ("土地覆盖背景识别显示，", False), (str(land_cover_context.get("visual_title") or "已完成地表背景识别"), True), ("。", False),
    ]
    if total > 0 and matched > 0:
        pieces += [("本次共 ", False), (_fmt_int(matched), True), (" 条观测成功匹配地表背景，占有效观测的 ", False), (f"{matched / total * 100:.1f}%", True), ("。", False)]
    if land_cover_context.get("guidance"):
        pieces += [(str(land_cover_context.get("guidance")), False)]
    return pieces


def _forecast_action_text(tone: str) -> str:
    if tone == "alert":
        return "优先查看近期已有火点且重复活跃的县区，必要时安排重点核查。"
    if tone == "watch":
        return "保持对当前活跃县区的巡查，先看重复活跃位置和农田背景火点。"
    if tone == "easing":
        return "可维持常规查看，但已有持续活跃位置仍应保留在巡查清单中。"
    return "按当前重点区域继续查看即可。"


def _weather_paragraphs(weather_context: dict[str, Any] | None) -> list[list[tuple[str, bool]]]:
    if not weather_context or not weather_context.get("available"):
        return []
    result: list[list[tuple[str, bool]]] = []
    mode = str(weather_context.get("mode") or "")
    source = str(weather_context.get("source") or "")
    if mode == "historical":
        period = weather_context.get("period") or {}
        metrics = period.get("metrics") or {}
        temp = _safe_float(metrics.get("temperature_c"))
        humidity = _safe_float(metrics.get("humidity_percent"))
        wind = _safe_float(metrics.get("wind_mps"))
        rain = _safe_float(metrics.get("precipitation_mm"))
        result.append([
            ("本次任务的天气背景采用 ", False), (source or "NASA POWER Daily", True),
            ("。任务期平均气温约 ", False), (f"{temp:.1f}℃" if temp is not None else "—", True),
            ("，平均湿度约 ", False), (f"{humidity:.0f}%" if humidity is not None else "—", True),
            ("，平均风速约 ", False), (f"{wind:.1f} m/s" if wind is not None else "—", True),
            ("，日均降水约 ", False), (f"{rain:.1f} mm" if rain is not None else "—", True), ("。", False),
        ])
        peak = weather_context.get("peak_day") or {}
        if peak.get("date"):
            result.append([("火点增多日 ", False), (str(peak.get("date")), True), (" 的天气表现为：", False), (str(peak.get("summary") or "天气条件接近任务期平均"), True)])
        counties = weather_context.get("counties") or []
        if counties:
            pieces: list[tuple[str, bool]] = [("重点县区中，", False)]
            for i, row in enumerate(counties[:3]):
                if i:
                    pieces.append(("；", False))
                pieces += [(str(row.get("county_name") or "重点县区"), True), (" 为", False), (str(row.get("condition") or "已取得天气背景"), True)]
            pieces.append(("。这些天气信息可与火点高值日期和持续活跃位置一起查看。", False))
            result.append(pieces)
        return result
    result.append([("近期天气评估来自 ", False), (source or "NOAA GFS", True), ("，当前总体判断为 ", False), (str(weather_context.get("overall") or "未来天气条件已更新"), True), ("。", False)])
    for horizon in (weather_context.get("horizons") or [])[:3]:
        hours = horizon.get("hours")
        state = str(horizon.get("state") or "天气条件已更新")
        summary = str(horizon.get("summary") or "")
        tone = str(horizon.get("tone") or "normal")
        counties = [str(row.get("county_name")) for row in (horizon.get("counties") or []) if row.get("county_name")][:3]
        pieces = [(f"未来 {hours} 小时，", False), (state, True), ("。", False)]
        if summary:
            pieces.append((summary, False))
        pieces += [("平台建议：", False), (_forecast_action_text(tone), True)]
        if counties:
            pieces += [("重点查看 ", False), ("、".join(counties), True), ("。", False)]
        result.append(pieces)
    return result


def _final_paragraph(analysis_summary: dict[str, Any], firms_intelligence: dict[str, Any], historical_baseline: dict[str, Any]) -> list[tuple[str, bool]]:
    summary = firms_intelligence.get("summary") or {}
    if analysis_summary.get("area_mode") == "coordinates_only":
        return [
            ("本次火点活动高值日期为 ", False),
            (str(summary.get("peak_date") or "暂无"), True),
            ("，当日观测 ", False),
            (_fmt_int(summary.get("peak_count")), True),
            (" 条。优先结合上方最密集经纬网格与重复活跃位置查看，"
             "再结合耕地背景及已配置的农事时段判断农业活动相关性。", False),
        ]
    priority = historical_baseline.get("priority_regions", []) if historical_baseline else []
    names = "、".join(str(row.get("region_name")) for row in priority[:3] if row.get("region_name"))
    pieces: list[tuple[str, bool]] = [
        ("综合来看，本次分析最需要抓住三项信息：", False),
        (str(analysis_summary.get("main_region") or "重点地区"), True), (" 是火点数量最集中的区域；", False),
        (str(summary.get("peak_date") or "峰值日期"), True), (" 是时间序列中最突出的高值日；历史同期判断为 ", False),
        (str(historical_baseline.get("province_status") or "暂无历史同期判断") if historical_baseline and historical_baseline.get("available") else "暂无历史同期判断", True), ("。", False),
    ]
    if names:
        pieces += [("后续核查可优先从 ", False), (names, True), (" 入手，再结合高值日期、持续活跃位置、地表背景和天气条件逐步缩小范围。", False)]
    else:
        pieces += [("后续可先从火点最集中区域入手，再结合高值日期、持续活跃位置、地表背景和天气条件逐步缩小范围。", False)]
    return pieces


def _observation_detail_tables(
    doc: Document, spatial_context: dict[str, Any],
) -> None:
    """Add independently informative day-window and FRP evidence."""
    diagnostics = spatial_context.get("diagnostics") or {}
    windows = diagnostics.get("weekly_windows") or []
    if windows:
        _heading(doc, "任务期分段观测变化")
        _paragraph(doc, [
            ("有效观测日期覆盖 ", True),
            (f"{diagnostics['active_days']} / {diagnostics['calendar_days']} 天，", False),
            ("有记录日期占比 ", False),
            (f"{diagnostics['active_day_share']:.1f}%。", True),
            ("将日期分段统计，可以区分火点集中出现的时间段，"
             "并据此回看各段卫星影像与区域分布。", False),
        ])
        table = doc.add_table(rows=1, cols=4)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for cell, title in zip(table.rows[0].cells, (
            "日期区间", "观测数", "占任务观测", "有观测日期"
        )):
            _shade(cell, SHADE)
            _set_cell_border(cell)
            _set_run_font(cell.paragraphs[0].add_run(title), size=9, bold=True)
        for period in windows:
            cells = table.add_row().cells
            entries = (
                f"{period['start']} 至 {period['end']}",
                f"{_fmt_int(period['count'])} 条",
                f"{period['share_percent']:.1f}%",
                f"{period['active_days']} 天",
            )
            for cell, value in zip(cells, entries):
                _set_cell_border(cell)
                cell.paragraphs[0].paragraph_format.space_after = Pt(0)
                _set_run_font(cell.paragraphs[0].add_run(value), size=9)
        busiest = sorted(windows, key=lambda row: (
            -row["count"], row["start"],
        ))[0]
        peak = diagnostics.get("peak_day") or {}
        _paragraph(doc, [
            ("任务期间观测最集中的时间段为 ", False),
            (f"{busiest['start']} 至 {busiest['end']}", True),
            (f"，包含 {_fmt_int(busiest['count'])} 条观测，"
             f"占有效日期观测总数的 {busiest['share_percent']:.1f}%。", False),
            ("单日观测最多的是 ", False),
            (str(peak.get("date") or "—"), True),
            (f"（{_fmt_int(peak.get('count'))} 条，"
             f"占 {float(peak.get('share_percent') or 0):.1f}%）；", False),
            (f"观测量最高的三个日期合计占 "
             f"{diagnostics.get('top_three_days_share'):.1f}%。"
             "这有助于优先选择需要复核的影像日期。", False),
        ])
    frp = diagnostics.get("frp")
    if frp:
        _heading(doc, "火点热辐射功率与高值观测")
        _paragraph(doc, [
            ("本次具有有效 FRP 数值的观测共 ", False),
            (_fmt_int(frp["count"]), True),
            (" 条；中位数 ", False),
            (f"{frp['median']:.2f} MW", True),
            ("、第 90 百分位 ", False),
            (f"{frp['p90']:.2f} MW", True),
            ("、最大记录值 ", False),
            (f"{frp['maximum']:.2f} MW。", True),
            ("这些数值是单次卫星观测的辐射量指标，"
             "不能直接换算焚烧面积或累计燃烧规模。", False),
        ])
        _paragraph(doc, [
            ("建议复核下列 FRP 较高观测的具体位置与时间，"
             "对照同日影像及附近其他火点，"
             "检查是否由固定热源、不同地表背景或集中热异常造成。", False),
        ])
        for index, item in enumerate(frp["top_observations"], 1):
            day = item["date"] or "日期未记录"
            _paragraph(doc, [
                (f"第 {index} 处：", True),
                (f"{day}，东经 {item['longitude']:.5f}°、"
                 f"北纬 {item['latitude']:.5f}°，"
                 f"FRP {item['frp']:.2f} MW。", False),
            ], after=3)


def build_analysis_report_docx(*, task: dict[str, Any], analysis_summary: dict[str, Any], firms_intelligence: dict[str, Any], historical_baseline: dict[str, Any], land_cover_context: dict[str, Any], priority_land_cover: dict[str, Any] | None, weather_context: dict[str, Any] | None, daily_series: list[dict[str, Any]], agricultural_relevance: dict[str, Any] | None = None, spatial_context: dict[str, Any] | None = None) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run("农业秸秆焚烧区域火点检测与分析平台分析报告")
    _set_run_font(r, size=16, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)
    report_name = str(task.get("name") or "分析任务")
    period = str(analysis_summary.get("period") or "")
    period_dates = re.findall(r"\d{4}-\d{2}-\d{2}", period)
    subtitle = report_name
    if period and not (period_dates and all(date in report_name for date in period_dates)):
        subtitle += "    " + period
    r = p.add_run(subtitle)
    _set_run_font(r, size=10.5)

    task_parameters = task.get("parameters") or {}
    selected_list = task_parameters.get("selected_regions") or []
    if selected_list:
        _paragraph(doc, [
            ("本次分析范围：", True),
            ("、".join(str(item["name"]) for item in selected_list), False),
        ])
    elif task_parameters.get("selected_region"):
        selected = task_parameters["selected_region"]
        _paragraph(doc, [("本次分析区域：", True), (str(selected.get("name") or "—"), False)])

    if task_parameters.get("area_mode") == "coordinates_only":
        declared = str(task_parameters.get("declared_area_label") or "").strip()
        if declared and declared != "本次上传数据范围":
            _paragraph(doc, [("分析区域：", True), (declared, False)])
        if task_parameters.get("requested_bbox"):
            _paragraph(doc, [
                ("筛选矩形（西、南、东、北）：", True),
                (", ".join(str(v) for v in task_parameters["requested_bbox"]), False),
            ])

    _summary_table(doc, analysis_summary, historical_baseline, firms_intelligence)
    if analysis_summary.get("area_mode") == "coordinates_only" and (
        spatial_context or {}
    ).get("top_grids"):
        top = spatial_context["top_grids"][0]
        fw, fs, fe, fn = top["bbox"]
        _heading(doc, "本次重点")
        _paragraph(doc, [
            ("优先查看：", True),
            (f"东经 {fw:.2f}°～{fe:.2f}°、北纬 {fs:.2f}°～{fn:.2f}°", True),
            ("；本次共记录 ", False),
            (_fmt_int(top.get("count")), True),
            (" 条观测。", False),
            ((f"其中 {top['peak_date']} 为该网格观测高值日。")
             if top.get("peak_date") else "", False),
        ], after=9)
    figure_number = 1

    if spatial_context and spatial_context.get("available"):
        _heading(doc, "空间位置与火点分布")
        west, south, east, north = spatial_context["bbox"]
        _paragraph(doc, [
            ("观测经度：", True),
            (f"{west:.5f}°E ～ {east:.5f}°E；", False),
            ("观测纬度：", True),
            (f"{south:.5f}°N ～ {north:.5f}°N。", False),
        ])
        region_rows = spatial_context.get("regions") or []
        if region_rows:
            top = region_rows[:5]
            _paragraph(doc, [
                ("底图匹配位置：", True),
                ("；".join(
                    f"{r['name']} {_fmt_int(r['count'])} 条（{r['share_percent']:.1f}%）"
                    for r in top
                ) + "。", False),
            ])
            _paragraph(doc, [
                ("地理位置数据：", True),
                (str(spatial_context.get("source") or "已安装 GeoJSON") + "；", False),
                ("匹配点位 ", True),
                (_fmt_int(spatial_context.get("matched")) + " / "
                 + _fmt_int(spatial_context.get("total")) + " 条。", False),
            ], after=6)
        elif spatial_context.get("has_geographic_background"):
            _paragraph(doc, [("本次火点不在已安装底图面要素的有效覆盖内。", False)])
        else:
            _paragraph(doc, [("当前位置图依据 FIRMS 观测经纬度绘制。", False)])
        map_bytes = spatial_context.get("map_png")
        if map_bytes:
            picture = doc.add_paragraph()
            picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
            picture.paragraph_format.keep_with_next = True
            picture.paragraph_format.keep_together = True
            picture.add_run().add_picture(BytesIO(map_bytes), width=Cm(16.5))
            caption_detail = "红色点为 FIRMS 观测坐标"
            if spatial_context.get("has_geographic_background"):
                caption_detail += "，蓝色线为已安装地图轮廓"
            caption_detail += (
                "；地图数字 1～5 对应下方统计网格中心，"
                "实测观测点的坐标见核查清单；"
                "橙色框为首位重点网格，其余网格以蓝色框表示；"
                "经纬度采用 WGS84。"
            )
            _paragraph(doc, [
                (f"图{figure_number} 本次火点空间分布。", True),
                (caption_detail, False),
            ], size=9.5, after=6)
            figure_number += 1
            if spatial_context.get("plotted_points", 0) < spatial_context.get("total", 0):
                _paragraph(doc, [
                    (f"图中展示 {_fmt_int(spatial_context['plotted_points'])} 个抽样点；"
                     "地区统计包含全部有效坐标观测。", False),
                ], size=9.5, after=5)
        focus = spatial_context.get("focus_grid")
        if focus:
            _heading(doc, "优先核查位置与建议")
            grids = spatial_context.get("top_grids") or []
            if grids:
                top_three = sum(int(item["count"]) for item in grids[:3])
                total = int(spatial_context.get("total") or 0)
                _paragraph(doc, [
                    (f"共涉及 {_fmt_int(spatial_context.get('total_grid_cells'))} 个 0.25° 经纬网格，", False),
                    ("观测最多的前三个网格共 ", False),
                    (_fmt_int(top_three), True),
                    (f" 条，占有效观测的 {100 * top_three / total if total else 0:.1f}%。", False),
                ], after=5)
                _spatial_hotspot_table(doc, grids)
                _paragraph(doc, [
                    ("表1 优先核查位置和建议。", True),
                    ("序号与图1地图标记一一对应，按照观测数量排序；"
                     "实测点为该网格高值日期的一条真实 FIRMS 观测，"
                     "用于查找影像，不代表整个网格或农田地块边界。", False),
                ], size=9.5, after=6)


    _heading(doc, "总体情况")
    _paragraph(doc, _overall_paragraph(analysis_summary, firms_intelligence))
    top_region_rows = [(str(row.get("region_name") or "—"), int(row.get("observation_count") or 0)) for row in _top_regions(firms_intelligence.get("regions") or [], 5)]
    if analysis_summary.get("area_mode") != "coordinates_only" and top_region_rows:
        _visual_bar_table(doc, top_region_rows, f"图{figure_number} 重点地区火点观测数量对比")
        figure_number += 1

    grid_summary = analysis_summary.get("location_groups") or {}
    if (
        analysis_summary.get("area_mode") == "coordinates_only"
        and grid_summary.get("cell_count", 0) > 1
        and not (spatial_context and spatial_context.get("available"))
    ):
        _heading(doc, "观测位置分组")
        _paragraph(doc, [(grid_summary.get("note") or "", False)])
        for group in grid_summary.get("groups", []):
            _paragraph(doc, [
                (str(group["label"]) + "：", True),
                (_fmt_int(group["count"]) + " 条观测", False),
            ], after=3)
        if grid_summary.get("other_count"):
            _paragraph(doc, [
                ("其余网格：", True),
                (_fmt_int(grid_summary["other_count"]) + " 条观测", False),
            ], after=3)

    _heading(doc, "时间变化")
    _paragraph(doc, _time_paragraph(firms_intelligence))
    top_dates = sorted(daily_series, key=lambda row: int(row.get("active_fire_observation_count") or 0), reverse=True)[:5]
    top_date_rows = [(str(row.get("date") or "—"), int(row.get("active_fire_observation_count") or 0)) for row in top_dates]
    if top_date_rows:
        _visual_bar_table(
            doc, top_date_rows, f"图{figure_number} 火点高值日期对比",
        )
        figure_number += 1

    if spatial_context and spatial_context.get("diagnostics"):
        _observation_detail_tables(doc, spatial_context)

    if analysis_summary.get("area_mode") != "coordinates_only":
        _heading(doc, "当前评估与重点核查")
        _paragraph(doc, _assessment_paragraph(
            historical_baseline, firms_intelligence, priority_land_cover,
        ))

    land = _land_paragraph(land_cover_context)
    if land:
        _heading(doc, "地表背景")
        _paragraph(doc, land)

    if (agricultural_relevance and agricultural_relevance.get("available")
            and not (spatial_context or {}).get("top_grids")):
        # With spatial data, per-grid actions already provide the next step.
        # Keep this fallback only for reports without a location checklist.
        _heading(doc, "农业地表核查建议")
        hotspot_rows = (
            (spatial_context or {}).get("top_grids") or []
        )
        farmland_rows = [
            row for row in hotspot_rows
            if int(row.get("cropland_background_count") or 0) > 0
        ]
        if farmland_rows:
            first = farmland_rows[0]
            fw, fs, fe, fn = first["bbox"]
            _paragraph(doc, [
                ("建议重点核对：", True),
                (f"东经 {fw:.2f}°～{fe:.2f}°、北纬 {fs:.2f}°～{fn:.2f}°"
                 " 网格内的耕地背景位置；", False),
                ("查阅该位置对应日期的卫星影像及当地田间作业记录，"
                 "确认具体地块和热异常来源。", False),
            ])
        elif hotspot_rows:
            first = hotspot_rows[0]
            fw, fs, fe, fn = first["bbox"]
            _paragraph(doc, [
                ("建议首先核对：", True),
                (f"东经 {fw:.2f}°～{fe:.2f}°、北纬 {fs:.2f}°～{fn:.2f}°"
                 " 网格的实际地表类型，", False),
                ("再比对火点日期的卫星影像及当地农事活动记录。", False),
            ])
        else:
            _paragraph(doc, [
                ("核查时将火点坐标与耕地分布、同期影像及农事作业记录叠加对照。", False),
            ])

    weather_blocks = _weather_paragraphs(weather_context)
    if weather_blocks:
        _heading(doc, "天气情况")
        for block in weather_blocks:
            _paragraph(doc, block)

    # Coordinate-task next steps are now present in the three-column
    # location table; repeating the same advice at the end adds no value.
    if not (analysis_summary.get("area_mode") == "coordinates_only"
            and (spatial_context or {}).get("top_grids")):
        _heading(doc, "综合分析")
        _paragraph(doc, _final_paragraph(
            analysis_summary, firms_intelligence, historical_baseline,
        ))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(12)
    r = p.add_run("生成时间：" + datetime.now().strftime("%Y-%m-%d %H:%M"))
    _set_run_font(r, size=10)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()
