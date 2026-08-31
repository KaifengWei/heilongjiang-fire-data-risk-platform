"""将边界、FIRMS CSV、既有烧毁像元 CSV 和 MCD64 TIF 写入统一数据库。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from fire_monitor.core.firms import fetch_firms_area_csv, normalized_firms_rows
from fire_monitor.core.geography import RegionIndex, load_regions_from_geojson
from fire_monitor.core.mcd64 import extract_mcd64_burned_pixels
from fire_monitor.storage.database import Database


def read_csv_with_fallback(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """兼容现有成果中常见的 UTF-8-SIG、UTF-8 和 GBK 编码。"""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error or RuntimeError(f"无法读取 CSV：{path}")


def _first_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).strip().lower().lstrip("\ufeff"): column for column in frame.columns}
    for candidate in candidates:
        match = lookup.get(candidate.lower())
        if match is not None:
            return match
    return None


def _as_float(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


class ImportService:
    def __init__(self, database: Database):
        self.database = database
        self.database.initialize()

    def import_regions(
        self,
        path: str | Path,
        *,
        source: str | None = None,
        version: str | None = None,
        name_field: str | None = None,
        region_name: str | None = None,
        level: str = "city",
    ) -> dict[str, Any]:
        regions = load_regions_from_geojson(
            path,
            source=source,
            version=version,
            name_field=name_field,
            region_name=region_name,
            level=level,
        )
        return {"stored_regions": self.database.upsert_regions(regions), "names": [r["name"] for r in regions]}

    def _region_index(self) -> RegionIndex:
        regions = self.database.list_regions()
        if not regions:
            raise RuntimeError("尚未导入行政区边界。请先执行 init-regions。")
        return RegionIndex(regions)

    def import_firms_dataframe(
        self,
        frame: pd.DataFrame,
        *,
        firms_source: str,
        source_ref: str,
        quality_only: bool = True,
        region_column: str | None = None,
    ) -> dict[str, Any]:
        index = self._region_index()
        known_regions = {region["name"] for region in index.regions}
        resolved_region_column = _first_column(frame, [region_column]) if region_column else None
        if region_column and not resolved_region_column:
            raise ValueError(f"FIRMS CSV 中找不到指定的区域列：{region_column}")
        run_id = self.database.start_import(
            "active_fire_observations",
            source_ref,
            metadata={
                "firms_source": firms_source,
                "quality_only": quality_only,
                "region_assignment": f"source column: {resolved_region_column}" if resolved_region_column else "point-in-polygon",
            },
        )
        input_count = len(frame)
        try:
            rows: list[dict[str, Any]] = []
            rejected_outside_regions = 0
            normalized_count = 0
            for row in normalized_firms_rows(
                frame,
                firms_source=firms_source,
                quality_only=quality_only,
                region_column=resolved_region_column,
            ):
                normalized_count += 1
                source_region_name = row.pop("source_region_name", None)
                if resolved_region_column:
                    region_name = source_region_name if source_region_name in known_regions else None
                else:
                    region_name = index.locate(row["longitude"], row["latitude"])
                if not region_name:
                    rejected_outside_regions += 1
                    continue
                row["region_name"] = region_name
                rows.append(row)
            stored = self.database.insert_active_fire_rows(rows, run_id)
            metadata = {
                "firms_source": firms_source,
                "quality_only": quality_only,
                "normalized_rows": normalized_count,
                "outside_configured_regions": rejected_outside_regions,
                "quality_rule": "VIIRS:n/h; MODIS:confidence>=30" if quality_only else "未执行质量筛选",
                "region_assignment": f"source column: {resolved_region_column}" if resolved_region_column else "point-in-polygon",
            }
            self.database.finish_import(run_id, input_count, stored, metadata=metadata)
            return {"run_id": run_id, "input_rows": input_count, "stored_rows": stored, **metadata}
        except Exception as exc:
            self.database.fail_import(run_id, str(exc))
            raise

    def import_firms_csv(
        self,
        path: str | Path,
        *,
        firms_source: str,
        quality_only: bool = True,
        region_column: str | None = None,
    ) -> dict[str, Any]:
        frame = read_csv_with_fallback(path, low_memory=False)
        return self.import_firms_dataframe(
            frame,
            firms_source=firms_source,
            source_ref=str(Path(path).resolve()),
            quality_only=quality_only,
            region_column=region_column,
        )

    def fetch_and_import_firms(
        self,
        *,
        firms_source: str,
        bbox: str,
        start,
        end,
        quality_only: bool = True,
    ) -> dict[str, Any]:
        frame = fetch_firms_area_csv(
            source=firms_source,
            bbox=bbox,
            start=start,
            end=end,
        )
        return self.import_firms_dataframe(
            frame,
            firms_source=firms_source,
            source_ref=f"FIRMS Area API: {firms_source}; bbox={bbox}; {start}..{end}",
            quality_only=quality_only,
            region_column=None,
        )

    def import_existing_burned_pixel_csv(
        self,
        path: str | Path,
        *,
        source_product: str = "已有火烧迹地像元成果",
    ) -> dict[str, Any]:
        """导入当前 2025-11 已验证成果中的烧毁像元明细 CSV。

        该入口用于接续已存在的可追溯结果；原始 MCD64 TIF 应使用
        :meth:`import_mcd64_tif` 重新计算。
        """
        frame = read_csv_with_fallback(path, low_memory=False)
        city_col = _first_column(frame, ["城市", "city", "region_name"])
        date_col = _first_column(frame, ["日期", "date", "burned_date"])
        doy_col = _first_column(frame, ["年积日doy", "doy"])
        lon_col = _first_column(frame, ["经度", "longitude", "lon"])
        lat_col = _first_column(frame, ["纬度", "latitude", "lat"])
        area_col = _first_column(
            frame,
            ["当前经纬网格面积_km2", "cell_area_km2", "grid_area_km2", "面积_km2"],
        )
        required = {"城市": city_col, "日期": date_col, "经度": lon_col, "纬度": lat_col, "面积": area_col}
        missing = [name for name, column in required.items() if not column]
        if missing:
            raise ValueError(f"烧毁像元 CSV 缺少必要列：{', '.join(missing)}")

        known_regions = {region["name"] for region in self.database.list_regions()}
        if not known_regions:
            raise RuntimeError("尚未导入行政区边界。请先执行 init-regions。")
        run_id = self.database.start_import(
            "burned_pixels_csv", str(Path(path).resolve()), metadata={"source_product": source_product}
        )
        try:
            rows: list[dict[str, Any]] = []
            skipped = 0
            for raw in frame.to_dict(orient="records"):
                region_name = str(raw.get(city_col, "")).strip()
                parsed_date = pd.to_datetime(raw.get(date_col), errors="coerce")
                lon = _as_float(raw.get(lon_col))
                lat = _as_float(raw.get(lat_col))
                area = _as_float(raw.get(area_col))
                if (
                    not region_name
                    or region_name not in known_regions
                    or pd.isna(parsed_date)
                    or lon is None
                    or lat is None
                    or area is None
                    or area < 0
                ):
                    skipped += 1
                    continue
                date_text = parsed_date.date().isoformat()
                doy = int(raw[doy_col]) if doy_col and pd.notna(raw.get(doy_col)) else None
                key_parts = [source_product, date_text, f"{lon:.8f}", f"{lat:.8f}", f"{area:.8f}"]
                rows.append(
                    {
                        "dedupe_key": hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest(),
                        "burned_date": date_text,
                        "doy": doy,
                        "latitude": lat,
                        "longitude": lon,
                        "region_name": region_name,
                        "cell_area_km2": area,
                        "source_product": source_product,
                        "raster_name": Path(path).name,
                        "qa_value": None,
                    }
                )
            stored = self.database.insert_burned_pixel_rows(rows, run_id)
            metadata = {"source_product": source_product, "skipped_rows": skipped, "mode": "已有明细成果接续导入"}
            self.database.finish_import(run_id, len(frame), stored, metadata=metadata)
            return {"run_id": run_id, "input_rows": len(frame), "stored_rows": stored, **metadata}
        except Exception as exc:
            self.database.fail_import(run_id, str(exc))
            raise

    def import_mcd64_tif(
        self,
        path: str | Path,
        *,
        product: str = "MCD64A1",
        qa_path: str | Path | None = None,
        chunk_rows: int = 256,
    ) -> dict[str, Any]:
        index = self._region_index()
        run_id = self.database.start_import(
            "burned_pixels_tif",
            str(Path(path).resolve()),
            metadata={"product": product, "qa_path": str(qa_path) if qa_path else None},
        )
        try:
            rows, metadata = extract_mcd64_burned_pixels(
                path,
                region_index=index,
                product=product,
                qa_path=qa_path,
                chunk_rows=chunk_rows,
            )
            stored = self.database.insert_burned_pixel_rows(rows, run_id)
            self.database.finish_import(run_id, len(rows), stored, metadata=metadata)
            return {"run_id": run_id, "input_rows": len(rows), "stored_rows": stored, **metadata}
        except Exception as exc:
            self.database.fail_import(run_id, str(exc))
            raise
