from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

from osgeo import ogr, osr
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


CITY_CODE_NAMES = {
    "2301": "哈尔滨市",
    "2302": "齐齐哈尔市",
    "2303": "鸡西市",
    "2304": "鹤岗市",
    "2305": "双鸭山市",
    "2306": "大庆市",
    "2307": "伊春市",
    "2308": "佳木斯市",
    "2309": "七台河市",
    "2310": "牡丹江市",
    "2311": "黑河市",
    "2312": "绥化市",
    "2327": "大兴安岭地区",
}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Build a compact Heilongjiang county/district GeoJSON "
            "from official 1:1M BOUA source data."
        )
    )

    parser.add_argument(
        "--source-root",
        required=True,
        help=(
            "Directory containing official source ZIPs, "
            "extracted .gdb folders, GeoPackages or BOUA.shp files."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(
            root
            / "data"
            / "regions"
            / "heilongjiang_county.geojson"
        ),
    )
    parser.add_argument(
        "--metadata-output",
        default=str(
            root
            / "data"
            / "regions"
            / "heilongjiang_county_metadata.json"
        ),
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=128,
    )
    parser.add_argument(
        "--simplify",
        type=float,
        default=0.0015,
    )

    return parser.parse_args()


def _field_name(layer, wanted: str) -> str | None:
    definition = layer.GetLayerDefn()

    for index in range(
        definition.GetFieldCount()
    ):
        field = definition.GetFieldDefn(index)

        if (
            field.GetName().upper()
            == wanted.upper()
        ):
            return field.GetName()

    return None


def discover_sources(
    root: Path,
    temporary_root: Path,
) -> list[Path]:
    """Recursively extract nested official ZIP packages."""

    candidates: list[Path] = []
    extracted_zip_keys: set[str] = set()

    zip_queue = list(root.rglob("*.zip"))

    while zip_queue:
        zip_path = zip_queue.pop(0)

        try:
            zip_key = str(zip_path.resolve())
        except OSError:
            zip_key = str(zip_path)

        if zip_key in extracted_zip_keys:
            continue

        extracted_zip_keys.add(zip_key)

        relative_name = zip_path.stem
        parent_key = abs(
            hash(str(zip_path.parent))
        ) % 100000000

        extract_dir = (
            temporary_root
            / f"{parent_key:08d}"
            / relative_name
        )

        extract_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(
            zip_path
        ) as archive:
            archive.extractall(
                extract_dir
            )

        for nested_zip in extract_dir.rglob(
            "*.zip"
        ):
            try:
                nested_key = str(
                    nested_zip.resolve()
                )
            except OSError:
                nested_key = str(
                    nested_zip
                )

            if (
                nested_key
                not in extracted_zip_keys
            ):
                zip_queue.append(
                    nested_zip
                )

    for search_root in (
        root,
        temporary_root,
    ):
        for path in search_root.rglob("*"):
            lower = path.name.lower()

            if (
                path.is_dir()
                and lower.endswith(".gdb")
            ):
                candidates.append(path)

            elif (
                path.is_file()
                and lower == "boua.shp"
            ):
                candidates.append(path)

            elif (
                path.is_file()
                and path.suffix.lower()
                in {".gpkg", ".sqlite"}
            ):
                candidates.append(path)

    unique = []
    seen = set()

    for path in candidates:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)

        if key in seen:
            continue

        seen.add(key)
        unique.append(path)

    return unique


def iter_boua_layers(path: Path):
    dataset = ogr.Open(
        str(path),
        0,
    )

    if dataset is None:
        return

    for index in range(
        dataset.GetLayerCount()
    ):
        layer = dataset.GetLayerByIndex(
            index
        )

        if (
            layer is not None
            and layer.GetName().upper()
            == "BOUA"
        ):
            yield dataset, layer


def transform_geometry(
    geometry,
    source_srs,
):
    geometry = geometry.Clone()

    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)

    if hasattr(
        target,
        "SetAxisMappingStrategy",
    ):
        target.SetAxisMappingStrategy(
            osr.OAMS_TRADITIONAL_GIS_ORDER
        )

    if source_srs is None:
        return geometry

    source = source_srs.Clone()

    if hasattr(
        source,
        "SetAxisMappingStrategy",
    ):
        source.SetAxisMappingStrategy(
            osr.OAMS_TRADITIONAL_GIS_ORDER
        )

    if not source.IsSame(target):
        transform = (
            osr.CoordinateTransformation(
                source,
                target,
            )
        )

        geometry.Transform(
            transform
        )

    return geometry


def collect_counties(
    source_paths: list[Path],
):
    grouped = defaultdict(list)
    names: dict[str, str] = {}
    source_feature_count = 0

    for path in source_paths:
        for dataset, layer in iter_boua_layers(
            path
        ):
            pac_field = _field_name(
                layer,
                "PAC",
            )
            name_field = _field_name(
                layer,
                "NAME",
            )

            if (
                pac_field is None
                or name_field is None
            ):
                continue

            source_srs = (
                layer.GetSpatialRef()
            )

            layer.ResetReading()

            for feature in layer:
                raw_pac = (
                    feature.GetField(
                        pac_field
                    )
                )
                raw_name = (
                    feature.GetField(
                        name_field
                    )
                )

                if (
                    raw_pac is None
                    or raw_name is None
                ):
                    continue

                pac = str(
                    raw_pac
                ).strip()

                if pac.endswith(".0"):
                    pac = pac[:-2]

                pac = pac.zfill(6)

                if (
                    len(pac) != 6
                    or not pac.startswith("23")
                    or pac.endswith("00")
                    or pac[:4]
                    not in CITY_CODE_NAMES
                ):
                    continue

                geometry = (
                    feature.GetGeometryRef()
                )

                if geometry is None:
                    continue

                geometry = (
                    transform_geometry(
                        geometry,
                        source_srs,
                    )
                )

                try:
                    shp = shape(
                        json.loads(
                            geometry.ExportToJson()
                        )
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                if shp.is_empty:
                    continue

                if not shp.is_valid:
                    shp = shp.buffer(0)

                if shp.is_empty:
                    continue

                grouped[pac].append(
                    shp
                )
                names[pac] = str(
                    raw_name
                ).strip()

                source_feature_count += 1

            dataset = None

    return (
        grouped,
        names,
        source_feature_count,
    )


def main() -> None:
    args = parse_args()

    source_root = (
        Path(args.source_root)
        .expanduser()
        .resolve()
    )

    output = (
        Path(args.output)
        .expanduser()
        .resolve()
    )

    metadata_output = (
        Path(args.metadata_output)
        .expanduser()
        .resolve()
    )

    if not source_root.exists():
        raise FileNotFoundError(
            source_root
        )

    with tempfile.TemporaryDirectory(
        prefix="heilongjiang-county-source-"
    ) as temporary:
        source_paths = discover_sources(
            source_root,
            Path(temporary),
        )

        if not source_paths:
            raise RuntimeError(
                "No BOUA source found. "
                "Expected official ZIPs, .gdb folders, "
                "GeoPackages or BOUA.shp."
            )

        (
            grouped,
            names,
            source_feature_count,
        ) = collect_counties(
            source_paths
        )

    if (
        len(grouped)
        != args.expected_count
    ):
        raise RuntimeError(
            f"Expected {args.expected_count} "
            "unique Heilongjiang county PAC codes, "
            f"but found {len(grouped)}. "
            "Do not continue with incomplete data."
        )

    features = []

    for pac in sorted(grouped):
        merged = unary_union(
            grouped[pac]
        )

        if args.simplify > 0:
            merged = merged.simplify(
                args.simplify,
                preserve_topology=True,
            )

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": names[pac],
                    "pac": pac,
                    "city_name": (
                        CITY_CODE_NAMES[
                            pac[:4]
                        ]
                    ),
                },
                "geometry": mapping(
                    merged
                ),
            }
        )

    payload = {
        "type": "FeatureCollection",
        "features": features,
    }

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    metadata_output.write_text(
        json.dumps(
            {
                "name": "黑龙江省县级行政区边界",
                "level": "county",
                "region_count": len(
                    features
                ),
                "source_dataset": (
                    "1:100万公众版基础地理信息数据（2021）"
                ),
                "source_provider": (
                    "全国地理信息资源目录服务系统"
                ),
                "source_layer": "BOUA",
                "source_actuality": "2019",
                "geometry_crs": "EPSG:4326",
                "source_feature_count": (
                    source_feature_count
                ),
                "simplify_tolerance_degrees": (
                    args.simplify
                ),
                "output_file": output.name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "County boundary context ready."
    )
    print()
    print(
        f"Counties/districts: "
        f"{len(features)}"
    )
    print(
        f"Source BOUA rows used: "
        f"{source_feature_count}"
    )
    print(f"Output: {output}")
    print(
        f"Metadata: "
        f"{metadata_output}"
    )


if __name__ == "__main__":
    main()
