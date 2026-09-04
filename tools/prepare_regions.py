from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from osgeo import ogr, osr

ogr.UseExceptions()
from shapely import from_wkb, make_valid, to_wkb
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw_regions"
    / "official_1m"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "regions"
)

OUTPUT_GEOJSON = (
    OUTPUT_DIR
    / "heilongjiang_city.geojson"
)

OUTPUT_METADATA = (
    OUTPUT_DIR
    / "metadata.json"
)


REQUIRED_SHEETS = {
    "N51",
    "N52",
    "M51",
    "M52",
    "M53",
    "L51",
    "L52",
    "L53",
    "K52",
}


CITY_INFO = {
    "2301": {
        "code": "230100",
        "name": "哈尔滨",
        "fullname": "哈尔滨市",
    },
    "2302": {
        "code": "230200",
        "name": "齐齐哈尔",
        "fullname": "齐齐哈尔市",
    },
    "2303": {
        "code": "230300",
        "name": "鸡西",
        "fullname": "鸡西市",
    },
    "2304": {
        "code": "230400",
        "name": "鹤岗",
        "fullname": "鹤岗市",
    },
    "2305": {
        "code": "230500",
        "name": "双鸭山",
        "fullname": "双鸭山市",
    },
    "2306": {
        "code": "230600",
        "name": "大庆",
        "fullname": "大庆市",
    },
    "2307": {
        "code": "230700",
        "name": "伊春",
        "fullname": "伊春市",
    },
    "2308": {
        "code": "230800",
        "name": "佳木斯",
        "fullname": "佳木斯市",
    },
    "2309": {
        "code": "230900",
        "name": "七台河",
        "fullname": "七台河市",
    },
    "2310": {
        "code": "231000",
        "name": "牡丹江",
        "fullname": "牡丹江市",
    },
    "2311": {
        "code": "231100",
        "name": "黑河",
        "fullname": "黑河市",
    },
    "2312": {
        "code": "231200",
        "name": "绥化",
        "fullname": "绥化市",
    },
    "2327": {
        "code": "232700",
        "name": "大兴安岭",
        "fullname": "大兴安岭地区",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def validate_cgcs2000_geographic(
    spatial_ref: osr.SpatialReference,
    *,
    sheet: str,
) -> None:
    """
    验证官方 FileGDB 中的 BOUA 是否为 CGCS2000 地理坐标系。

    FileGDB 使用 ESRI 风格 WKT，
    不一定携带 EPSG:4490 authority，
    因此不能只依赖 SpatialReference.IsSame(EPSG:4490)。
    """

    if spatial_ref is None:
        raise RuntimeError(
            f"{sheet}/BOUA 没有空间参考。"
        )

    spatial_ref = spatial_ref.Clone()

    spatial_ref.SetAxisMappingStrategy(
        osr.OAMS_TRADITIONAL_GIS_ORDER
    )

    if not spatial_ref.IsGeographic():
        raise RuntimeError(
            f"{sheet}/BOUA 不是地理坐标系。"
        )

    geogcs_name = (
        spatial_ref.GetAttrValue("GEOGCS")
        or ""
    ).upper()

    datum_name = (
        spatial_ref.GetAttrValue("DATUM")
        or ""
    ).upper()

    semi_major = (
        spatial_ref.GetSemiMajor()
    )

    inv_flattening = (
        spatial_ref.GetInvFlattening()
    )

    name_matches = (
        (
            "CGCS" in geogcs_name
            and "2000" in geogcs_name
        )
        or (
            "2000" in datum_name
        )
    )

    ellipsoid_matches = (
        abs(
            semi_major
            - 6378137.0
        )
        < 0.001
        and
        abs(
            inv_flattening
            - 298.257222101
        )
        < 0.000001
    )

    if not (
        name_matches
        and ellipsoid_matches
    ):
        raise RuntimeError(
            f"{sheet}/BOUA 不是预期的 "
            "CGCS2000 地理坐标系。"
            f" GEOGCS={geogcs_name!r},"
            f" DATUM={datum_name!r},"
            f" semi_major={semi_major},"
            f" inv_flattening={inv_flattening}"
        )

def build_transform() -> osr.CoordinateTransformation:
    """
    CGCS2000 geographic coordinates
    EPSG:4490
        ↓
    WGS84 longitude/latitude
    EPSG:4326
    """

    source = osr.SpatialReference()
    source.ImportFromEPSG(4490)

    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)

    # GDAL 3+ 默认可能使用 EPSG 轴顺序。
    # 本项目统一使用 longitude, latitude。
    source.SetAxisMappingStrategy(
        osr.OAMS_TRADITIONAL_GIS_ORDER
    )

    target.SetAxisMappingStrategy(
        osr.OAMS_TRADITIONAL_GIS_ORDER
    )

    return osr.CoordinateTransformation(
        source,
        target,
    )


def polygonal_only(geometry):
    """
    MakeValid 后如果出现 GeometryCollection，
    仅保留其中的 Polygon / MultiPolygon。
    """

    if isinstance(
        geometry,
        (Polygon, MultiPolygon),
    ):
        return geometry

    polygons = []

    if isinstance(
        geometry,
        GeometryCollection,
    ):
        for part in geometry.geoms:
            polygonal = polygonal_only(part)

            if polygonal is None:
                continue

            if isinstance(
                polygonal,
                Polygon,
            ):
                polygons.append(polygonal)

            elif isinstance(
                polygonal,
                MultiPolygon,
            ):
                polygons.extend(
                    list(polygonal.geoms)
                )

    if not polygons:
        return None

    return unary_union(polygons)


def extract_inner_packages(
    temporary_dir: Path,
) -> dict[str, Path]:
    outer_packages = sorted(
        SOURCE_DIR.glob("*.zip")
    )

    if not outer_packages:
        raise FileNotFoundError(
            "未在 data/raw_regions/official_1m "
            "找到官方数据 ZIP。"
        )

    inner_packages: dict[str, Path] = {}

    outer_dir = (
        temporary_dir
        / "outer_packages"
    )
    outer_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for outer_path in outer_packages:
        with zipfile.ZipFile(
            outer_path,
            "r",
        ) as archive:
            archive.extractall(
                outer_dir
            )

    for inner_path in sorted(
        outer_dir.glob("*.gdb.zip")
    ):
        sheet = inner_path.name.removesuffix(
            ".gdb.zip"
        )

        if sheet in inner_packages:
            raise RuntimeError(
                f"发现重复图幅：{sheet}"
            )

        inner_packages[sheet] = inner_path

    missing = (
        REQUIRED_SHEETS
        - set(inner_packages)
    )

    if missing:
        raise RuntimeError(
            "缺少必要图幅："
            + ", ".join(
                sorted(missing)
            )
        )

    return {
        sheet: inner_packages[sheet]
        for sheet in sorted(
            REQUIRED_SHEETS
        )
    }


def extract_gdb(
    inner_package: Path,
    temporary_dir: Path,
) -> Path:
    sheet = inner_package.name.removesuffix(
        ".gdb.zip"
    )

    target_dir = (
        temporary_dir
        / "gdb"
        / sheet
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        inner_package,
        "r",
    ) as archive:
        archive.extractall(
            target_dir
        )

    gdb_path = (
        target_dir
        / f"{sheet}.gdb"
    )

    if not gdb_path.exists():
        candidates = list(
            target_dir.rglob("*.gdb")
        )

        if len(candidates) != 1:
            raise RuntimeError(
                f"{sheet} 中无法唯一确定 FileGDB。"
            )

        gdb_path = candidates[0]

    return gdb_path


def read_boua(
    gdb_path: Path,
    *,
    sheet: str,
    grouped_geometries: dict[str, list[Any]],
    county_codes: set[str],
) -> int:
    dataset = ogr.Open(
        str(gdb_path),
        0,
    )

    if dataset is None:
        raise RuntimeError(
            f"无法打开 FileGDB：{gdb_path}"
        )

    layer = dataset.GetLayerByName(
        "BOUA"
    )

    if layer is None:
        raise RuntimeError(
            f"{sheet} 缺少 BOUA 图层。"
        )

    layer_srs = layer.GetSpatialRef()

    validate_cgcs2000_geographic(
        layer_srs,
        sheet=sheet,
    )

    accepted = 0

    layer.ResetReading()

    for feature in layer:
        pac_value = feature.GetField(
            "PAC"
        )

        if pac_value is None:
            continue

        try:
            pac = str(
                int(pac_value)
            ).zfill(6)

        except (
            TypeError,
            ValueError,
        ):
            continue

        # 只保留黑龙江省县级行政区代码。
        if not pac.startswith("23"):
            continue

        group_code = pac[:4]

        if group_code not in CITY_INFO:
            continue

        geometry = feature.GetGeometryRef()

        if geometry is None:
            continue

        shapely_geometry = from_wkb(
            bytes(
                geometry.ExportToWkb()
            )
        )

        if shapely_geometry.is_empty:
            continue

        if not shapely_geometry.is_valid:
            shapely_geometry = make_valid(
                shapely_geometry
            )

        shapely_geometry = polygonal_only(
            shapely_geometry
        )

        if (
                shapely_geometry is None
                or shapely_geometry.is_empty
        ):
            print(
                f"[跳过] {sheet}: "
                f"PAC={pac} "
                "为零面积/退化边缘几何"
            )
            continue

        if shapely_geometry.area <= 0:
            print(
                f"[跳过] {sheet}: "
                f"PAC={pac} "
                "面面积为 0"
            )
            continue

        grouped_geometries[
            group_code
        ].append(
            shapely_geometry
        )

        county_codes.add(pac)

        accepted += 1

    feature = None
    layer = None
    dataset = None

    return accepted


def transform_geometry_to_wgs84(
    geometry,
    transformation,
) -> dict[str, Any]:
    ogr_geometry = (
        ogr.CreateGeometryFromWkb(
            bytes(
                to_wkb(geometry)
            )
        )
    )

    if ogr_geometry is None:
        raise RuntimeError(
            "无法创建 OGR 几何。"
        )

    result = ogr_geometry.Transform(
        transformation
    )

    if result != 0:
        raise RuntimeError(
            "CGCS2000 → WGS84 坐标转换失败。"
        )

    return json.loads(
        ogr_geometry.ExportToJson()
    )


def build_features(
    grouped_geometries: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    expected_groups = set(
        CITY_INFO
    )

    actual_groups = set(
        grouped_geometries
    )

    if actual_groups != expected_groups:
        missing = (
            expected_groups
            - actual_groups
        )

        extra = (
            actual_groups
            - expected_groups
        )

        raise RuntimeError(
            "地级行政区分组不完整。"
            f" missing={sorted(missing)},"
            f" extra={sorted(extra)}"
        )

    transformation = (
        build_transform()
    )

    features = []

    for group_code in sorted(
        CITY_INFO
    ):
        parts = grouped_geometries[
            group_code
        ]

        merged = unary_union(
            parts
        )

        if not merged.is_valid:
            merged = make_valid(
                merged
            )

        merged = polygonal_only(
            merged
        )

        if (
            merged is None
            or merged.is_empty
        ):
            raise RuntimeError(
                f"{group_code} 合并后几何为空。"
            )

        if not merged.is_valid:
            raise RuntimeError(
                f"{group_code} 合并后几何无效。"
            )

        info = CITY_INFO[
            group_code
        ]

        geometry_json = (
            transform_geometry_to_wgs84(
                merged,
                transformation,
            )
        )

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": (
                        info["fullname"]
                    ),
                    "short_name": (
                        info["name"]
                    ),
                    "fullname": (
                        info["fullname"]
                    ),
                    "code": (
                        info["code"]
                    ),
                    "level": 2,
                },
                "geometry": (
                    geometry_json
                ),
            }
        )

    if len(features) != 13:
        raise RuntimeError(
            "最终行政区数量不是 13。"
        )

    return features


def main() -> None:
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"原始数据目录不存在："
            f"{SOURCE_DIR}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    grouped_geometries = defaultdict(
        list
    )

    county_codes: set[str] = set()

    accepted_rows = 0

    with tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True,
    ) as temp:
        temporary_dir = Path(temp)

        inner_packages = (
            extract_inner_packages(
                temporary_dir
            )
        )

        for sheet, package in (
            inner_packages.items()
        ):
            gdb_path = extract_gdb(
                package,
                temporary_dir,
            )

            count = read_boua(
                gdb_path,
                sheet=sheet,
                grouped_geometries=(
                    grouped_geometries
                ),
                county_codes=(
                    county_codes
                ),
            )

            accepted_rows += count

            print(
                f"[读取] {sheet}: "
                f"{count} 条黑龙江 BOUA 记录"
            )

    features = build_features(
        grouped_geometries
    )

    source_packages = []

    for path in sorted(
        SOURCE_DIR.glob("*.zip")
    ):
        source_packages.append(
            {
                "filename": path.name,
                "sha256": (
                    sha256_file(path)
                ),
            }
        )

    feature_collection = {
        "type": "FeatureCollection",
        "properties": {
            "name": "黑龙江",
            "fullname": "黑龙江省",
            "code": "230000",
            "level": 1,
        },
        "meta": {
            "dataset": (
                "1:100万公众版基础地理信息数据（2021）"
            ),
            "provider": (
                "全国地理信息资源目录服务系统"
            ),
            "source_layer": "BOUA",
            "source_crs": (
                "CGCS2000 / EPSG:4490"
            ),
            "output_crs": (
                "WGS84 / EPSG:4326"
            ),
            "processing": (
                "筛选 PAC=23xxxx 的 BOUA 面，"
                "按 PAC 前四位归并为 13 个地级行政单元，"
                "再转换至 EPSG:4326。"
            ),
            "source_url": (
                "https://www.webmap.cn/"
                "commres.do?method=result25W"
            ),
            "source_actuality": "2019",
            "attribution": (
                "数据来源：全国地理信息资源目录服务系统"
            ),
            "sheets": sorted(
                REQUIRED_SHEETS
            ),
        },
        "features": features,
    }

    OUTPUT_GEOJSON.write_text(
        json.dumps(
            feature_collection,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    metadata = {
        "name": (
            "黑龙江省地级行政区边界"
        ),
        "level": "city",
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
        "source_crs": (
            "EPSG:4490"
        ),
        "source_url": (
            "https://www.webmap.cn/"
            "commres.do?method=result25W"
        ),
        "source_actuality": "2019",
        "attribution": (
            "数据来源：全国地理信息资源目录服务系统"
        ),
        "geometry_crs": (
            "EPSG:4326"
        ),
        "source_sheets": sorted(
            REQUIRED_SHEETS
        ),
        "source_packages": (
            source_packages
        ),
        "source_boua_rows": (
            accepted_rows
        ),
        "unique_county_pac": len(
            county_codes
        ),

        "processing": {
            "province_filter": (
                "PAC startswith 23"
            ),
            "grouping": (
                "PAC first four digits"
            ),
            "geometry_operation": (
                "polygon union/dissolve"
            ),
            "coordinate_conversion": (
                "EPSG:4490 -> EPSG:4326"
            ),
        },
        "output_file": (
            "heilongjiang_city.geojson"
        ),
    }

    OUTPUT_METADATA.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "[完成] "
        f"{OUTPUT_GEOJSON}"
    )

    print(
        "[完成] "
        f"{OUTPUT_METADATA}"
    )

    print(
        "[统计] BOUA记录："
        f"{accepted_rows}"
    )

    print(
        "[统计] 不重复县级PAC："
        f"{len(county_codes)}"
    )

    print(
        "[统计] 地级行政区："
        f"{len(features)}"
    )


if __name__ == "__main__":
    main()