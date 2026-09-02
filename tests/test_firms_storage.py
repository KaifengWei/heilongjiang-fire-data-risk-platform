# Day4B：FIRMS规范观测数据库存储、NRT/SP来源追溯与首选来源更新测试

import pandas as pd

from fire_monitor.core.firms import (
    normalize_firms_dataframe,
)
from fire_monitor.storage.database import (
    Database,
)
from fire_monitor.storage.firms_repository import (
    FirmsRepository,
)


def _row(
    *,
    version: str,
    satellite: str = "N",
):
    return {
        "latitude": 45.75,
        "longitude": 126.65,
        "acq_date": "2026-03-15",
        "acq_time": 325,
        "instrument": "VIIRS",
        "satellite": satellite,
        "confidence": "n",
        "version": version,
        "frp": 8.5,
    }


def _normalize(
    *,
    firms_source: str,
    version: str,
    satellite: str = "N",
):
    result = normalize_firms_dataframe(
        pd.DataFrame(
            [
                _row(
                    version=version,
                    satellite=satellite,
                )
            ]
        ),
        firms_source=firms_source,
        quality_only=True,
    )

    return result.rows


def test_nrt_then_sp_keeps_one_observation(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    repository = FirmsRepository(
        database
    )

    nrt_rows = _normalize(
        firms_source="VIIRS_SNPP_NRT",
        version="2.0NRT",
    )

    sp_rows = _normalize(
        firms_source="VIIRS_SNPP_SP",
        version="2.0",
    )

    first = repository.store_rows(
        nrt_rows
    )

    second = repository.store_rows(
        sp_rows
    )

    assert (
        first.inserted_observations
        == 1
    )

    assert (
        second.inserted_observations
        == 0
    )

    assert (
        second.existing_observations
        == 1
    )

    assert (
        second.preferred_source_updates
        == 1
    )

    canonical_key = (
        nrt_rows[0]["dedupe_key"]
    )

    observation = (
        repository.get_observation(
            canonical_key
        )
    )

    assert observation is not None

    assert (
        observation[
            "processing_class"
        ]
        == "SP"
    )

    assert (
        observation[
            "firms_source"
        ]
        == "VIIRS_SNPP_SP"
    )

    sources = repository.list_sources(
        canonical_key
    )

    assert len(sources) == 2

    assert {
        item["processing_class"]
        for item in sources
    } == {
        "NRT",
        "SP",
    }


def test_sp_is_not_replaced_by_later_nrt(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    repository = FirmsRepository(
        database
    )

    sp_rows = _normalize(
        firms_source="VIIRS_SNPP_SP",
        version="2.0",
    )

    nrt_rows = _normalize(
        firms_source="VIIRS_SNPP_NRT",
        version="2.0NRT",
    )

    repository.store_rows(
        sp_rows
    )

    result = repository.store_rows(
        nrt_rows
    )

    assert (
        result.preferred_source_updates
        == 0
    )

    observation = (
        repository.get_observation(
            sp_rows[0]["dedupe_key"]
        )
    )

    assert observation is not None

    assert (
        observation[
            "processing_class"
        ]
        == "SP"
    )


def test_same_source_record_is_not_stored_twice(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    repository = FirmsRepository(
        database
    )

    rows = _normalize(
        firms_source="VIIRS_SNPP_NRT",
        version="2.0NRT",
    )

    repository.store_rows(rows)

    second = repository.store_rows(
        rows
    )

    assert (
        second.existing_observations
        == 1
    )

    assert (
        second.source_records_added
        == 0
    )

    assert (
        second.source_records_existing
        == 1
    )

    sources = repository.list_sources(
        rows[0]["dedupe_key"]
    )

    assert len(sources) == 1


def test_different_satellite_creates_new_observation(
    tmp_path,
):
    database = Database(
        tmp_path / "test.sqlite"
    )

    repository = FirmsRepository(
        database
    )

    first_rows = _normalize(
        firms_source="VIIRS_SNPP_NRT",
        version="2.0NRT",
        satellite="N",
    )

    second_rows = _normalize(
        firms_source="VIIRS_NOAA20_NRT",
        version="2.0NRT",
        satellite="J1",
    )

    repository.store_rows(
        first_rows
    )

    result = repository.store_rows(
        second_rows
    )

    assert (
        result.inserted_observations
        == 1
    )

    with database.connect() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM active_fire_observations
            """
        ).fetchone()[0]

    assert count == 2