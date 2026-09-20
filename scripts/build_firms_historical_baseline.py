from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fire_monitor.services.historical_baseline_service import (  # noqa: E402
    HistoricalFirmsBaselineBuilder,
)


def parse_years(value: str) -> list[int]:
    text = value.strip()

    if "-" in text:
        start_text, end_text = text.split("-", 1)
        start = int(start_text)
        end = int(end_text)

        if end < start:
            raise argparse.ArgumentTypeError(
                "年份范围结束值不能早于开始值。"
            )

        return list(range(start, end + 1))

    return [
        int(item.strip())
        for item in text.split(",")
        if item.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "把真实 NASA FIRMS Archive NOAA-20 CSV "
            "构建为黑龙江历史同期基线。"
        )
    )

    parser.add_argument(
        "csv",
        nargs="+",
        help="一个或多个 NASA FIRMS Archive CSV 路径。",
    )
    parser.add_argument(
        "--regions",
        default=str(
            ROOT / "data" / "regions" / "heilongjiang_city.geojson"
        ),
        help="黑龙江市级 GeoJSON。",
    )
    parser.add_argument(
        "--years",
        type=parse_years,
        default=list(range(2019, 2026)),
        help="声明完整下载的历史年份，例如 2019-2025。",
    )
    parser.add_argument(
        "--output",
        default=str(
            ROOT
            / "data"
            / "baselines"
            / "firms_noaa20_daily.json"
        ),
        help="基线输出 JSON。",
    )

    args = parser.parse_args()

    builder = HistoricalFirmsBaselineBuilder(
        region_geojson_path=args.regions,
        expected_years=args.years,
    )

    payload = builder.build(
        args.csv,
        output_path=args.output,
    )

    print("Historical FIRMS baseline built successfully.")
    print("Output:", args.output)
    print("Years:", ", ".join(map(str, payload["expected_years"])))
    print(
        "Accepted observations:",
        payload["report"].get("accepted_baseline_observations", 0),
    )
    print(
        "Science-quality rows skipped:",
        payload["report"].get("non_science_quality_rows", 0),
    )
    print(
        "Outside Heilongjiang:",
        payload["report"].get("outside_regions", 0),
    )


if __name__ == "__main__":
    main()
