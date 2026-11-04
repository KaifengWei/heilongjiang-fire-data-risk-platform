"""Build and optionally install one offline outline from real BOUA sources.

Example (from the original project folder, in the fire-monitor environment):
python scripts/prepare_official_basemap.py --input "D:\\Data\\Official1M" \\
    --expected-sources 77 --source "1:100万公众版基础地理信息数据(2021)" \\
    --output "D:\\Data\\firms_reference.geojson" --install --confirm-usage-rights

No external map is downloaded or distributed by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fire_monitor.services.basemap_preparation_service import (
    discover_sources,
    inspect_source,
    prepare_outline,
    write_geojson_atomic,
)
from fire_monitor.services.reference_basemap_service import (
    MAX_OUTPUT_BYTES, ReferenceBasemapStore,
)
from fire_monitor.user_data_paths import desktop_runtime_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="将已获取的 BOUA GIS 行政区面转换成离线 WGS84 轮廓。"
    )
    parser.add_argument("--input", type=Path, required=True, help="已解压的 .gdb 或所在目录")
    parser.add_argument("--layer", default="BOUA", help="图层名称，默认 BOUA；单层文件可用 auto")
    parser.add_argument("--inspect", action="store_true", help="只列出可读取图层，不生成地图")
    parser.add_argument("--source-epsg", type=int, help="仅在原图层无 CRS 时显式指定 EPSG")
    parser.add_argument("--simplify", type=float, default=0.01, help="轮廓简化容差（度）")
    parser.add_argument("--allow-missing-layer", action="store_true", help="略过缺少指定图层的图幅")
    parser.add_argument("--expected-sources", type=int, help="严格要求文件数，如官方全国完整分幅 77")
    parser.add_argument("--output", type=Path, help="生成可在结果页面导入的 GeoJSON 文件")
    parser.add_argument("--source", help="数据集来源，--install 时必填")
    parser.add_argument("--install", action="store_true", help="将实际转换结果安装到本机 EXE 的离线地图库")
    parser.add_argument("--confirm-usage-rights", action="store_true",
                        help="明确确认拥有本软件使用这些数据的权限")
    args = parser.parse_args(argv)

    if args.install and not args.confirm_usage_rights:
        parser.error("--install 必须附加 --confirm-usage-rights")
    if args.install and not args.source:
        parser.error("--install 必须提供 --source")
    if not args.output and not args.install and not args.inspect:
        parser.error("请提供 --output 和/或 --install")

    try:
        files = discover_sources(args.input, exclude=args.output)
        if not files:
            raise ValueError("输入目录中未找到解压后的 GIS 文件。")
        if args.inspect:
            for source in files:
                print(f"[{source}]")
                for layer in inspect_source(source):
                    print(f"  {layer['name']}: {layer['features']} 个要素；EPSG {layer['srs']}")
            return 0

        result = prepare_outline(
            files,
            layer_name=args.layer,
            source_epsg=args.source_epsg,
            simplify_degrees=args.simplify,
            allow_missing_layer=args.allow_missing_layer,
            expected_sources=args.expected_sources,
        )
        print(f"数据源：{result.source_files} 个；含行政区面的图幅：{result.files_with_polygons} 个")
        print(f"原始面要素：{result.input_polygons}；输出：{result.output_bytes} 字节")
        print(f"WGS84 坐标范围：{result.bounds}")
        if result.empty_files:
            print("无面或缺少图层的文件：")
            for name in result.empty_files:
                print(" ", name)
        if result.output_bytes > MAX_OUTPUT_BYTES - 4096:
            raise ValueError("输出文件过大，请提高 --simplify；未写入任何输出。")

        # Validate the exact output before updating the user's installed map.
        if args.install:
            local_appdata = os.environ.get("LOCALAPPDATA")
            if os.name != "nt" or not local_appdata:
                raise ValueError("--install 仅支持已配置 LOCALAPPDATA 的 Windows；其它平台请用 --output。")
            store = ReferenceBasemapStore(desktop_runtime_dir())
            result_installed = store.install(
                result.geojson,
                source=args.source,
                authorized=args.confirm_usage_rights,
            )
            print("已安装到：", store.path)
            print("来源校验 SHA256：", result_installed["sha256"])
        if args.output:
            output = write_geojson_atomic(args.output, result.geojson)
            print("已输出 GeoJSON：", output)
        return 0
    except (ValueError, OSError) as exc:
        print(f"地图处理失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
