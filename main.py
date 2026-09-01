"""本地运行入口与数据导入命令。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from fire_monitor.app import create_app  # noqa: E402
from fire_monitor.config import load_settings  # noqa: E402
from fire_monitor.services.import_service import ImportService  # noqa: E402
from fire_monitor.storage.database import Database  # noqa: E402


def add_database_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        help="SQLite 数据库路径；省略时使用 data/runtime/fire_monitor.sqlite。",
    )


def get_service(args: argparse.Namespace) -> ImportService:
    settings = load_settings(args.db)
    return ImportService(Database(settings.database_path))


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="黑龙江省火点数据检测与风险评估平台：本地运行与数据导入工具。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="启动本地浏览器界面")
    add_database_argument(serve)
    serve.add_argument("--host", default=None, help="默认 127.0.0.1")
    serve.add_argument("--port", type=int, default=None, help="默认 5050")

    regions = subparsers.add_parser("init-regions", help="导入 GeoJSON 行政区边界")
    add_database_argument(regions)
    regions.add_argument("--geojson", required=True, help="GeoJSON 文件路径")
    regions.add_argument("--name-field", help="一个文件含多个区域时使用的属性字段，例如 NL_NAME_2")
    regions.add_argument("--region-name", help="把文件全部要素合并为一个区域时指定名称")
    regions.add_argument("--level", default="city", choices=["province", "city", "county"])
    regions.add_argument("--source", help="边界来源说明")
    regions.add_argument("--version", help="边界版本或下载日期")

    firms = subparsers.add_parser("import-firms-csv", help="导入本地 FIRMS 主动火点 CSV")
    add_database_argument(firms)
    firms.add_argument("--file", required=True, help="FIRMS CSV 文件路径")
    firms.add_argument("--source", required=True, help="数据源标签，例如 VIIRS_SNPP_SP")
    firms.add_argument("--keep-all", action="store_true", help="不执行质量筛选，保留全部记录")
    firms.add_argument(
        "--region-column",
        help="可选：CSV 已按同一版本边界赋值时的区域列，例如 City。省略时按经纬度与已导入边界重新落区。",
    )

    fetch = subparsers.add_parser("fetch-firms", help="通过 FIRMS Area API 下载并导入主动火点")
    add_database_argument(fetch)
    fetch.add_argument("--source", required=True, help="例如 VIIRS_SNPP_NRT、VIIRS_NOAA20_SP、MODIS_SP")
    fetch.add_argument("--bbox", required=True, help="west,south,east,north")
    fetch.add_argument("--start", required=True, type=date.fromisoformat)
    fetch.add_argument("--end", required=True, type=date.fromisoformat)
    fetch.add_argument("--keep-all", action="store_true", help="不执行质量筛选，保留全部记录")

    burned_csv = subparsers.add_parser("import-burned-csv", help="导入既有烧毁像元明细 CSV")
    add_database_argument(burned_csv)
    burned_csv.add_argument("--file", required=True, help="烧毁像元明细 CSV")
    burned_csv.add_argument("--product", default="已有火烧迹地像元成果", help="产品名称")

    mcd64 = subparsers.add_parser("import-mcd64", help="从 MCD64 burndate TIF 提取烧毁像元和面积")
    add_database_argument(mcd64)
    mcd64.add_argument("--tif", required=True, help="MCD64 月度 burndate TIF")
    mcd64.add_argument("--product", default="MCD64A1", help="产品标签")
    mcd64.add_argument("--qa-tif", help="可选：对应 QA TIF")
    mcd64.add_argument("--chunk-rows", type=int, default=256, help="分块读取行数")

    status = subparsers.add_parser("status", help="查看当前数据库的导入状态")
    add_database_argument(status)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        settings = load_settings(args.db)
        app = create_app(settings.database_path)
        host = args.host or settings.host
        port = args.port or settings.port
        print(f"本地服务已启动：http://{host}:{port}")
        app.run(host=host, port=port, debug=False, use_reloader=False)
        return

    service = get_service(args)
    if args.command == "init-regions":
        emit(
            service.import_regions(
                args.geojson,
                source=args.source,
                version=args.version,
                name_field=args.name_field,
                region_name=args.region_name,
                level=args.level,
            )
        )
    elif args.command == "import-firms-csv":
        emit(
            service.import_firms_csv(
                args.file,
                firms_source=args.source,
                quality_only=not args.keep_all,
                region_column=args.region_column,
            )
        )
    elif args.command == "fetch-firms":
        emit(
            service.fetch_and_import_firms(
                firms_source=args.source,
                bbox=args.bbox,
                start=args.start,
                end=args.end,
                quality_only=not args.keep_all,
            )
        )
    elif args.command == "import-burned-csv":
        emit(service.import_existing_burned_pixel_csv(args.file, source_product=args.product))
    elif args.command == "import-mcd64":
        emit(
            service.import_mcd64_tif(
                args.tif,
                product=args.product,
                qa_path=args.qa_tif,
                chunk_rows=args.chunk_rows,
            )
        )
    elif args.command == "status":
        emit(service.database.data_status())


if __name__ == "__main__":
    main()
