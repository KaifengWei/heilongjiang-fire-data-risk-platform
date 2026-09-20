from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import time

import requests


API_ROOT = "https://firms.modaps.eosdis.nasa.gov/api"
SOURCE = "VIIRS_NOAA20_SP"
DEFAULT_BBOX = "120,42,136,55"
DEFAULT_START_YEAR = 2019
DEFAULT_END_YEAR = 2025
DAY_RANGE = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download NASA FIRMS NOAA-20 VIIRS standard-processing "
            "history for Heilongjiang in resumable 5-day chunks."
        )
    )

    parser.add_argument(
        "--out-dir",
        required=True,
        help=(
            "Directory OUTSIDE the git repository for raw history, "
            r"e.g. D:\FIRMS_History\NOAA20_SP"
        ),
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=DEFAULT_END_YEAR,
    )
    parser.add_argument(
        "--bbox",
        default=DEFAULT_BBOX,
        help="west,south,east,north",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help=(
            "After download, invoke the project's historical baseline "
            "builder and write data/baselines/firms_noaa20_daily.json."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help=(
            "Project root. Defaults to the parent of this script's "
            "scripts directory."
        ),
    )

    return parser.parse_args()


def map_key() -> str:
    value = os.environ.get("FIRMS_MAP_KEY", "").strip()

    if not value:
        raise SystemExit(
            "Environment variable FIRMS_MAP_KEY is not set.\n"
            "PowerShell example:\n"
            '  $env:FIRMS_MAP_KEY="YOUR_KEY"\n'
            "Do not paste the key into source files or commit it to git."
        )

    return value


def parse_csv_text(text: str) -> tuple[list[str], list[list[str]]]:
    text = text.lstrip("\ufeff").strip()

    if not text:
        return [], []

    reader = csv.reader(StringIO(text))
    rows = list(reader)

    if not rows:
        return [], []

    header = [item.strip() for item in rows[0]]
    return header, rows[1:]


def check_data_availability(
    session: requests.Session,
    key: str,
    *,
    end_year: int,
) -> None:
    url = f"{API_ROOT}/data_availability/csv/{key}/{SOURCE}"
    response = session.get(url, timeout=90)
    response.raise_for_status()

    reader = csv.DictReader(StringIO(response.text))

    rows = list(reader)

    if not rows:
        raise RuntimeError(
            "NASA FIRMS data-availability endpoint returned no rows."
        )

    row = rows[0]
    max_date_text = (
        row.get("max_date")
        or row.get("MAX_DATE")
        or ""
    ).strip()

    if not max_date_text:
        print(
            "Warning: could not read VIIRS_NOAA20_SP max_date; "
            "continuing with direct requests."
        )
        return

    max_date = date.fromisoformat(max_date_text)

    required = date(end_year, 12, 31)

    if max_date < required:
        raise RuntimeError(
            f"{SOURCE} currently reports standard-processing data only "
            f"through {max_date.isoformat()}, but {required.isoformat()} "
            "is required for the requested full-year baseline."
        )

    print(
        f"NASA availability check: {SOURCE} through "
        f"{max_date.isoformat()}."
    )


def chunk_starts(year: int):
    current = date(year, 1, 1)
    last = date(year, 12, 31)

    while current <= last:
        yield current
        current += timedelta(days=DAY_RANGE)


def fetch_chunk(
    session: requests.Session,
    key: str,
    bbox: str,
    start: date,
    output_path: Path,
) -> None:
    if output_path.is_file() and output_path.stat().st_size > 0:
        return

    remaining = (date(start.year, 12, 31) - start).days + 1
    day_range = min(DAY_RANGE, remaining)

    url = (
        f"{API_ROOT}/area/csv/{key}/{SOURCE}/"
        f"{bbox}/{day_range}/{start.isoformat()}"
    )

    last_error: Exception | None = None

    for attempt in range(1, 5):
        try:
            response = session.get(url, timeout=120)
            response.raise_for_status()

            text = response.text

            header, _ = parse_csv_text(text)

            if header and "latitude" not in {
                item.lower() for item in header
            }:
                raise RuntimeError(
                    "Unexpected FIRMS response header: "
                    + ",".join(header[:8])
                )

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output_path.write_text(
                text,
                encoding="utf-8",
            )
            return

        except (
            requests.RequestException,
            RuntimeError,
        ) as exc:
            last_error = exc

            if attempt >= 4:
                break

            wait_seconds = 2 ** attempt
            print(
                f"  retry {attempt}/3 after error: {exc}"
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"Failed FIRMS request starting {start.isoformat()}: "
        f"{last_error}"
    )


def merge_year(
    chunk_dir: Path,
    output_path: Path,
) -> tuple[int, list[str]]:
    chunk_files = sorted(chunk_dir.glob("*.csv"))

    header: list[str] | None = None
    rows_written = 0

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(handle)

        for path in chunk_files:
            chunk_header, rows = parse_csv_text(
                path.read_text(encoding="utf-8")
            )

            if not chunk_header:
                continue

            if header is None:
                header = chunk_header
                writer.writerow(header)
            elif chunk_header != header:
                raise RuntimeError(
                    f"CSV header mismatch: {path}"
                )

            for row in rows:
                if not row:
                    continue
                writer.writerow(row)
                rows_written += 1

    if header is None:
        # Keep an empty file out of the builder's input list.
        output_path.unlink(missing_ok=True)
        return 0, []

    return rows_written, header


def download_year(
    session: requests.Session,
    key: str,
    *,
    out_dir: Path,
    bbox: str,
    year: int,
) -> Path:
    chunk_dir = (
        out_dir
        / ".chunks"
        / str(year)
    )

    starts = list(chunk_starts(year))
    total = len(starts)

    print(f"\n{year}: {total} chunks")

    for index, start in enumerate(starts, start=1):
        output = (
            chunk_dir
            / f"{start.isoformat()}.csv"
        )

        if not (
            output.is_file()
            and output.stat().st_size > 0
        ):
            fetch_chunk(
                session,
                key,
                bbox,
                start,
                output,
            )

            # Be polite to the public service and avoid bursty requests.
            time.sleep(0.18)

        if (
            index == 1
            or index % 20 == 0
            or index == total
        ):
            print(
                f"  {index:>3}/{total} "
                f"through {start.isoformat()}"
            )

    merged = (
        out_dir
        / f"firms_noaa20_sp_{year}.csv"
    )

    count, header = merge_year(
        chunk_dir,
        merged,
    )

    print(
        f"  merged: {merged.name} "
        f"({count:,} rows)"
    )

    required = {
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "satellite",
        "instrument",
        "confidence",
        "version",
    }

    normalized_header = {
        value.lower()
        for value in header
    }

    missing = sorted(
        required - normalized_header
    )

    if missing:
        raise RuntimeError(
            f"{year} merged CSV is missing required columns: "
            + ", ".join(missing)
        )

    return merged


def build_baseline(
    project_root: Path,
    csv_paths: list[Path],
    start_year: int,
    end_year: int,
) -> None:
    builder = (
        project_root
        / "scripts"
        / "build_firms_historical_baseline.py"
    )

    if not builder.is_file():
        raise FileNotFoundError(
            f"Historical baseline builder not found: {builder}"
        )

    command = [
        sys.executable,
        str(builder),
        *[str(path) for path in csv_paths],
        "--years",
        f"{start_year}-{end_year}",
        "--output",
        str(
            project_root
            / "data"
            / "baselines"
            / "firms_noaa20_daily.json"
        ),
    ]

    print("\nBuilding compact historical baseline...")
    subprocess.run(
        command,
        cwd=project_root,
        check=True,
    )


def main() -> None:
    args = parse_args()

    if args.end_year < args.start_year:
        raise SystemExit(
            "--end-year cannot be earlier than --start-year."
        )

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    key = map_key()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "heilongjiang-fire-monitor/"
                "historical-baseline-builder"
            )
        }
    )

    check_data_availability(
        session,
        key,
        end_year=args.end_year,
    )

    print("Source:", SOURCE)
    print("BBox:", args.bbox)
    print(
        "Years:",
        f"{args.start_year}-{args.end_year}",
    )
    print("Raw history directory:", out_dir)
    print(
        "The MAP_KEY is read only from the environment "
        "and is never written to disk."
    )

    merged_files = []

    for year in range(
        args.start_year,
        args.end_year + 1,
    ):
        merged_files.append(
            download_year(
                session,
                key,
                out_dir=out_dir,
                bbox=args.bbox,
                year=year,
            )
        )

    print("\nHistorical download complete.")
    print("Merged files:")

    for path in merged_files:
        print(" -", path)

    if args.build:
        if args.project_root:
            project_root = (
                Path(args.project_root)
                .expanduser()
                .resolve()
            )
        else:
            project_root = (
                Path(__file__)
                .resolve()
                .parents[1]
            )

        build_baseline(
            project_root,
            merged_files,
            args.start_year,
            args.end_year,
        )

        print(
            "\nBaseline ready:",
            project_root
            / "data"
            / "baselines"
            / "firms_noaa20_daily.json",
        )
        print(
            "Restart the local application and open the "
            "2025 DAY13 task to inspect Historical Context."
        )


if __name__ == "__main__":
    main()
