from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import requests

try:
    from osgeo import gdal  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "GDAL is required. Run this script in the fire-monitor conda environment."
    ) from exc


CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
SHORT_NAME = "MCD12Q1"
VERSION = "061"
PROVIDER = "LPCLOUD"
YEAR = 2024
BBOX = "120,42,136,55"


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Download NASA MCD12Q1 V061 2024 data intersecting "
            "Heilongjiang and build a compact LC_Type1 GeoTIFF."
        )
    )
    parser.add_argument(
        "--raw-dir",
        required=True,
        help=r"Raw HDF directory outside git, e.g. D:\MCD12Q1_2024",
    )
    parser.add_argument(
        "--regions",
        default=str(root / "data" / "regions" / "heilongjiang_city.geojson"),
    )
    parser.add_argument(
        "--output",
        default=str(
            root / "data" / "context" / "mcd12q1_2024_lc_type1.tif"
        ),
    )
    parser.add_argument("--bbox", default=BBOX)
    parser.add_argument(
        "--preview-output",
        default=str(root / "static" / "context" / "mcd12q1_2024_landcover.png"),
    )
    return parser.parse_args()


def token() -> str:
    value = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not value:
        raise SystemExit(
            "EARTHDATA_TOKEN is not set.\n"
            'PowerShell: $env:EARTHDATA_TOKEN="YOUR_EARTHDATA_BEARER_TOKEN"\n'
            "Do not commit the token."
        )
    return value


def search_granules(session: requests.Session, bbox: str) -> list[dict]:
    params = {
        "provider": PROVIDER,
        "short_name": SHORT_NAME,
        "version": VERSION,
        "temporal": f"{YEAR}-01-01T00:00:00Z,{YEAR}-12-31T23:59:59Z",
        "bounding_box": bbox,
        "page_size": 200,
    }
    response = session.get(CMR_URL, params=params, timeout=90)
    response.raise_for_status()
    entries = response.json().get("feed", {}).get("entry", [])
    if not entries:
        raise RuntimeError("CMR returned no MCD12Q1 2024 granules.")
    return entries


def find_hdf_link(entry: dict) -> str:
    links = []
    for item in entry.get("links", []):
        href = str(item.get("href") or "").strip()
        lower = href.lower()
        if href and lower.endswith(".hdf") and "opendap" not in lower:
            links.append(href)

    if not links:
        raise RuntimeError(
            "No downloadable HDF link for "
            + str(entry.get("title") or entry.get("id") or "granule")
        )

    links.sort(
        key=lambda value: (
            "earthdatacloud.nasa.gov" not in value,
            value,
        )
    )
    return links[0]


def download(session: requests.Session, url: str, destination: Path) -> None:
    if destination.is_file() and destination.stat().st_size > 0:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    with session.get(
        url,
        stream=True,
        timeout=180,
        allow_redirects=True,
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)

    partial.replace(destination)


def lc_type1_subdataset(path: Path) -> str:
    dataset = gdal.Open(str(path), gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError(f"GDAL could not open {path}")

    for name, description in dataset.GetSubDatasets():
        normalized = (name + " " + description).replace(" ", "").lower()
        if "lc_type1" in normalized:
            return name

    raise RuntimeError(f"LC_Type1 not found in {path.name}")


def build_raster(
    hdf_files: list[Path],
    *,
    regions_path: Path,
    output_path: Path,
) -> None:
    if gdal.GetDriverByName("HDF4") is None:
        raise RuntimeError(
            "Current GDAL build has no HDF4 driver."
        )

    subdatasets = [lc_type1_subdataset(path) for path in hdf_files]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mcd12q1-lc-") as temp_dir:
        vrt_path = Path(temp_dir) / "mcd12q1_lc_type1.vrt"

        vrt = gdal.BuildVRT(
            str(vrt_path),
            subdatasets,
            resolution="highest",
        )
        if vrt is None:
            raise RuntimeError("Could not build MCD12Q1 LC_Type1 mosaic.")
        vrt = None

        options = gdal.WarpOptions(
            format="GTiff",
            dstSRS="EPSG:4326",
            resampleAlg="near",
            cutlineDSName=str(regions_path),
            cropToCutline=True,
            dstNodata=255,
            outputType=gdal.GDT_Byte,
            multithread=True,
            creationOptions=[
                "TILED=YES",
                "COMPRESS=DEFLATE",
                "PREDICTOR=2",
                "BIGTIFF=IF_SAFER",
            ],
        )

        result = gdal.Warp(
            str(output_path),
            str(vrt_path),
            options=options,
        )
        if result is None:
            raise RuntimeError("Could not create land-cover context raster.")

        result.SetMetadataItem("SOURCE_PRODUCT", "MCD12Q1.061")
        result.SetMetadataItem("SOURCE_YEAR", str(YEAR))
        result.SetMetadataItem("SOURCE_LAYER", "LC_Type1")
        result.SetMetadataItem("CLASSIFICATION", "IGBP")
        result = None


def build_preview(source_path: Path, destination: Path) -> None:
    source = gdal.Open(str(source_path), gdal.GA_ReadOnly)
    if source is None:
        raise RuntimeError(f"Could not open {source_path}")

    array = source.GetRasterBand(1).ReadAsArray()
    mem = gdal.GetDriverByName("MEM").Create(
        "", source.RasterXSize, source.RasterYSize, 1, gdal.GDT_Byte
    )
    mem.SetGeoTransform(source.GetGeoTransform())
    mem.SetProjection(source.GetProjection())
    band = mem.GetRasterBand(1)
    band.WriteArray(array)
    band.SetNoDataValue(255)

    table = gdal.ColorTable()
    colors = {
        0:(255,255,255,0),
        1:(55,113,67,255),2:(55,113,67,255),3:(67,126,73,255),4:(79,139,82,255),5:(92,148,89,255),
        6:(148,177,98,255),7:(159,186,107,255),8:(147,176,103,255),9:(157,188,112,255),10:(170,195,118,255),
        11:(107,170,184,255),12:(216,180,85,255),13:(144,138,149,255),14:(228,197,106,255),
        15:(224,229,226,255),16:(203,198,183,255),17:(95,157,183,255),255:(255,255,255,0)
    }
    for value, rgba in colors.items():
        table.SetColorEntry(value, rgba)

    band.SetRasterColorTable(table)
    band.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)

    destination.parent.mkdir(parents=True, exist_ok=True)
    width = 480
    height = max(1, round(source.RasterYSize * width / source.RasterXSize))

    result = gdal.Translate(
        str(destination), mem, format="PNG",
        width=width, height=height, resampleAlg="nearest", noData=255
    )
    if result is None:
        raise RuntimeError("Could not create land-cover preview PNG.")

def main() -> None:
    args = parse_args()
    raw_dir = Path(args.raw_dir).expanduser().resolve()
    regions = Path(args.regions).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    preview_output = Path(args.preview_output).expanduser().resolve()

    if not regions.is_file():
        raise FileNotFoundError(regions)

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token()}",
            "User-Agent": "heilongjiang-fire-monitor/mcd12q1-builder",
        }
    )

    entries = search_granules(session, args.bbox)

    print(f"CMR found {len(entries)} MCD12Q1 2024 granules.")

    hdf_files = []
    for index, entry in enumerate(entries, start=1):
        url = find_hdf_link(entry)
        filename = Path(url.split("?", 1)[0]).name
        destination = raw_dir / filename
        download(session, url, destination)
        hdf_files.append(destination)
        print(f"  {index}/{len(entries)} {filename}")

    build_raster(
        hdf_files,
        regions_path=regions,
        output_path=output,
    )

    build_preview(output, preview_output)

    dataset = gdal.Open(str(output), gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError("Output raster could not be reopened.")

    metadata = {
        "product": "MCD12Q1 V061",
        "year": YEAR,
        "layer": "LC_Type1",
        "classification": "IGBP",
        "width": dataset.RasterXSize,
        "height": dataset.RasterYSize,
        "source_granules": [path.name for path in hdf_files],
    }

    sidecar = output.with_suffix(".json")
    sidecar.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("Land-cover context ready:")
    print(output)
    print("Metadata:")
    print(sidecar)
    print()
    print("Raw HDF files remain outside the repository.")


if __name__ == "__main__":
    main()
