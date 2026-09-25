#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSS = ROOT / "static" / "product.css"
HOME_JS = ROOT / "static" / "home.js"
INDEX = ROOT / "templates" / "index.html"
BACKUP = ROOT / "data" / "runtime" / "home_blue_white_final_v1_backup"

CSS_OVERRIDE = '\n/* =========================================================\n   HOME BLUE WHITE FINAL V1\n   ========================================================= */\n\n.home-body {\n  background: #f6fbfd !important;\n}\n\n.home-workspace {\n  background: linear-gradient(180deg, #f8fcfe 0%, #eef7fb 100%) !important;\n}\n\n.home-landing {\n  color: #173a49 !important;\n  background:\n    radial-gradient(circle at 78% 18%, rgba(83, 176, 210, .16), transparent 31%),\n    radial-gradient(circle at 24% 78%, rgba(113, 174, 198, .09), transparent 29%),\n    linear-gradient(145deg, #fbfdfe 0%, #eef8fb 55%, #f8fcfd 100%) !important;\n}\n\n.home-hero-grid {\n  opacity: .55 !important;\n  background-image:\n    linear-gradient(rgba(58, 126, 151, .05) 1px, transparent 1px),\n    linear-gradient(90deg, rgba(58, 126, 151, .05) 1px, transparent 1px) !important;\n  background-size: 56px 56px !important;\n}\n\n.home-product-kicker {\n  color: #4e8092 !important;\n}\n\n.home-signal-dot {\n  background: #2a9dbc !important;\n  box-shadow:\n    0 0 0 4px rgba(42, 157, 188, .08),\n    0 0 14px rgba(42, 157, 188, .28) !important;\n}\n\n.home-hero-copy h1 {\n  color: #103847 !important;\n  text-shadow: none !important;\n}\n\n.home-hero-lead {\n  color: #4f6e79 !important;\n}\n\n.home-primary-action {\n  color: #ffffff !important;\n  background: linear-gradient(135deg, #2c91b3, #247f9f) !important;\n  border: 1px solid #247f9f !important;\n  box-shadow: 0 12px 28px rgba(36, 127, 159, .16) !important;\n}\n\n.home-primary-action:hover {\n  background: linear-gradient(135deg, #2787a7, #1f7391) !important;\n}\n\n.home-secondary-action {\n  color: #24586b !important;\n  background: rgba(255, 255, 255, .9) !important;\n  border: 1px solid rgba(61, 120, 143, .22) !important;\n}\n\n.home-secondary-action:hover {\n  background: #ffffff !important;\n  border-color: rgba(61, 120, 143, .34) !important;\n}\n\n.home-source-strip {\n  color: #6b8994 !important;\n}\n\n.home-source-strip i {\n  background: #8badb9 !important;\n}\n\n.home-hero-visual {\n  border: 1px solid rgba(70, 143, 170, .18) !important;\n  background:\n    linear-gradient(180deg, rgba(255, 255, 255, .97), rgba(239, 248, 251, .97)) !important;\n  box-shadow:\n    0 20px 56px rgba(46, 94, 112, .10),\n    inset 0 1px rgba(255, 255, 255, .94) !important;\n}\n\n.home-visual-topline {\n  color: #658490 !important;\n  border-bottom: 1px solid rgba(70, 143, 170, .12) !important;\n  background: rgba(246, 251, 253, .76) !important;\n}\n\n.home-visual-topline b {\n  color: #2a819f !important;\n}\n\n.home-visual-caption {\n  color: #587884 !important;\n  border-top: 1px solid rgba(70, 143, 170, .12) !important;\n  background: rgba(246, 251, 253, .76) !important;\n}\n\n.home-visual-caption small {\n  color: #8198a1 !important;\n}\n\n.home-capabilities {\n  border-top: 1px solid rgba(69, 139, 164, .13) !important;\n  background: rgba(255, 255, 255, .82) !important;\n}\n\n.home-capabilities article {\n  border-right: 1px solid rgba(69, 139, 164, .10) !important;\n}\n\n.home-capability-index {\n  color: #78a2b2 !important;\n}\n\n.home-capabilities h2 {\n  color: #245568 !important;\n}\n\n.home-capabilities p {\n  color: #68848f !important;\n}\n\n.app-sidebar {\n  background: #ffffff !important;\n  border-right: 1px solid #e3edf1 !important;\n}\n\n.app-brand-copy strong {\n  color: #163b4b !important;\n}\n\n.app-brand-copy small,\n.app-side-footer {\n  color: #728a94 !important;\n}\n\n.app-brand-mark {\n  background: linear-gradient(145deg, #2995a9, #238697) !important;\n  box-shadow: 0 8px 20px rgba(35, 134, 151, .16) !important;\n}\n'
HOME_JS_LIGHT = "(() => {\n  const canvas = document.getElementById('homeMapCanvas');\n  const node = document.getElementById('homeRegionFeatures');\n  if (!canvas || !node) return;\n\n  let collection = {};\n  try {\n    collection = JSON.parse(node.textContent || '{}');\n  } catch (_) {\n    return;\n  }\n\n  const features = Array.isArray(collection.features)\n    ? collection.features\n    : [];\n\n  function ringsOf(geometry) {\n    if (!geometry) return [];\n    if (geometry.type === 'Polygon') return geometry.coordinates || [];\n    if (geometry.type === 'MultiPolygon') return (geometry.coordinates || []).flat();\n    return [];\n  }\n\n  const all = [];\n  features.forEach(feature => {\n    ringsOf(feature.geometry).forEach(ring => {\n      ring.forEach(point => all.push(point));\n    });\n  });\n\n  if (!all.length) return;\n\n  const xs = all.map(point => Number(point[0]));\n  const ys = all.map(point => Number(point[1]));\n\n  const bounds = {\n    minX: Math.min(...xs),\n    maxX: Math.max(...xs),\n    minY: Math.min(...ys),\n    maxY: Math.max(...ys),\n  };\n\n  function centroid(feature) {\n    const points = [];\n    ringsOf(feature.geometry).forEach(ring => {\n      ring.forEach(point => points.push(point));\n    });\n\n    if (!points.length) return null;\n\n    return [\n      points.reduce((sum, point) => sum + Number(point[0]), 0) / points.length,\n      points.reduce((sum, point) => sum + Number(point[1]), 0) / points.length,\n    ];\n  }\n\n  const centers = features.map(centroid).filter(Boolean);\n  let phase = 0;\n\n  function draw() {\n    const rect = canvas.getBoundingClientRect();\n    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));\n    const width = Math.max(320, Math.round(rect.width || 620));\n    const height = Math.max(320, Math.round(rect.height || 520));\n\n    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {\n      canvas.width = width * dpr;\n      canvas.height = height * dpr;\n    }\n\n    const ctx = canvas.getContext('2d');\n    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);\n    ctx.clearRect(0, 0, width, height);\n\n    const pad = Math.max(30, width * .065);\n    const spanX = Math.max(.001, bounds.maxX - bounds.minX);\n    const spanY = Math.max(.001, bounds.maxY - bounds.minY);\n    const scale = Math.min(\n      (width - pad * 2) / spanX,\n      (height - pad * 2) / spanY\n    );\n    const ox = (width - spanX * scale) / 2;\n    const oy = (height - spanY * scale) / 2;\n\n    const project = point => [\n      ox + (Number(point[0]) - bounds.minX) * scale,\n      height - (oy + (Number(point[1]) - bounds.minY) * scale),\n    ];\n\n    ctx.strokeStyle = 'rgba(46, 125, 153, .54)';\n    ctx.fillStyle = 'rgba(80, 165, 194, .075)';\n    ctx.lineWidth = 1;\n\n    features.forEach(feature => {\n      ringsOf(feature.geometry).forEach(ring => {\n        if (!ring.length) return;\n\n        ctx.beginPath();\n        ring.forEach((point, index) => {\n          const [x, y] = project(point);\n          if (index === 0) ctx.moveTo(x, y);\n          else ctx.lineTo(x, y);\n        });\n        ctx.closePath();\n        ctx.fill();\n        ctx.stroke();\n      });\n    });\n\n    phase += .012;\n\n    centers.forEach((point, index) => {\n      const [x, y] = project(point);\n      const pulse = (Math.sin(phase * 4 + index * .83) + 1) / 2;\n      const outer = 4 + pulse * 6;\n\n      ctx.beginPath();\n      ctx.arc(x, y, outer, 0, Math.PI * 2);\n      ctx.strokeStyle = `rgba(38, 137, 169, ${.07 + pulse * .12})`;\n      ctx.stroke();\n\n      ctx.beginPath();\n      ctx.arc(x, y, 1.45 + pulse * .85, 0, Math.PI * 2);\n      ctx.fillStyle = `rgba(30, 115, 146, ${.52 + pulse * .34})`;\n      ctx.fill();\n    });\n\n    requestAnimationFrame(draw);\n  }\n\n  draw();\n})();\n"


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp_home_blue_white_final_v1")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def run_checked(cmd: list[str], label: str) -> None:
    print(f"\n==> {label}")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{label}失败，退出码：{result.returncode}")


def backup_all() -> None:
    if BACKUP.exists():
        shutil.rmtree(BACKUP)

    for path in (CSS, HOME_JS, INDEX):
        if not path.is_file():
            raise FileNotFoundError(f"缺少文件：{path}")

        dst = BACKUP / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def restore_all() -> None:
    for path in (CSS, HOME_JS, INDEX):
        src = BACKUP / path.relative_to(ROOT)
        if src.exists():
            shutil.copy2(src, path)


def main() -> int:
    backup_all()

    try:
        css = CSS.read_text(encoding="utf-8")

        marker = "/* =========================================================\n   HOME BLUE WHITE FINAL V1"
        if marker in css:
            css = css.split(marker, 1)[0].rstrip()

        atomic_write(CSS, css + "\n\n" + CSS_OVERRIDE.strip() + "\n")
        atomic_write(HOME_JS, HOME_JS_LIGHT)

        index = INDEX.read_text(encoding="utf-8")
        index = index.replace(">ONLINE</b>", ">LOCAL ANALYSIS</b>")
        atomic_write(INDEX, index)

        node = shutil.which("node")
        if node:
            run_checked(
                [node, "--check", str(HOME_JS)],
                "home.js 语法检查",
            )

        run_checked(
            [sys.executable, "-m", "pytest", "-q"],
            "完整 pytest",
        )

    except Exception:
        print("\n修改或验证失败，正在自动回滚……", file=sys.stderr)
        restore_all()
        print("已恢复首页修改前文件。", file=sys.stderr)
        raise

    print("\n========================================")
    print("首页蓝白最终配色 V1 已应用")
    print("========================================")
    print("已完成：")
    print(" - 深色首页强制覆盖为浅蓝白首页")
    print(" - 标题改为深蓝")
    print(" - 地图面板改为白色 / 浅蓝")
    print(" - 黑龙江轮廓及点位改为中蓝")
    print(" - 底部能力模块改为白色")
    print(" - ONLINE 改为 LOCAL ANALYSIS")
    print(" - 完整 pytest 已执行")
    print()
    print("先运行：python main.py serve")
    print("确认颜色正确后，再运行：.\\build_windows.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
