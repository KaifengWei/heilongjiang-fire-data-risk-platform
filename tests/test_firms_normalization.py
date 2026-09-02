# Day4A：FIRMS正式字段规范化、观测身份键与异常记录统计测试

import pandas as pd
import pytest

from fire_monitor.core.firms import (
    canonical_observation_key,
    infer_processing_class,
    normalize_acq_time,
    normalize_firms_dataframe,
)


def test_acq_time_is_normalized_to_four_digits():
    assert normalize_acq_time(3) == "0003"
    assert normalize_acq_time(35) == "0035"
    assert normalize_acq_time(930) == "0930"
    assert normalize_acq_time("1425") == "1425"

    assert (
        normalize_acq_time("2360")
        is None
    )

    assert (
        normalize_acq_time("2400")
        is None
    )


def test_processing_class_is_identified():
    assert (
        infer_processing_class(
            firms_source=(
                "VIIRS_SNPP_NRT"
            ),
            version="2.0NRT",
        )
        == "NRT"
    )

    assert (
        infer_processing_class(
            firms_source=(
                "VIIRS_SNPP_SP"
            ),
            version="2.0",
        )
        == "SP"
    )

    assert (
        infer_processing_class(
            firms_source="unknown",
            version=None,
        )
        == "UNKNOWN"
    )


def test_nrt_and_sp_share_same_canonical_key():
    common = {
        "latitude": 45.75,
        "longitude": 126.65,
        "acq_date": "2026-03-15",
        "acq_time": 325,
        "instrument": "VIIRS",
        "satellite": "N",
        "confidence": "n",
    }

    nrt_frame = pd.DataFrame(
        [
            {
                **common,
                "version": "2.0NRT",
            }
        ]
    )

    sp_frame = pd.DataFrame(
        [
            {
                **common,
                "version": "2.0",
            }
        ]
    )

    nrt = normalize_firms_dataframe(
        nrt_frame,
        firms_source="VIIRS_SNPP_NRT",
        quality_only=True,
    )

    sp = normalize_firms_dataframe(
        sp_frame,
        firms_source="VIIRS_SNPP_SP",
        quality_only=True,
    )

    assert (
        nrt.rows[0]["dedupe_key"]
        == sp.rows[0]["dedupe_key"]
    )

    assert (
        nrt.rows[0][
            "source_record_key"
        ]
        != sp.rows[0][
            "source_record_key"
        ]
    )

    assert (
        nrt.rows[0][
            "processing_class"
        ]
        == "NRT"
    )

    assert (
        sp.rows[0][
            "processing_class"
        ]
        == "SP"
    )


def test_different_satellites_are_not_duplicates():
    first = (
        canonical_observation_key(
            acquired_date=(
                "2026-03-15"
            ),
            acquired_time="0325",
            latitude=45.75,
            longitude=126.65,
            instrument="VIIRS",
            satellite="N",
        )
    )

    second = (
        canonical_observation_key(
            acquired_date=(
                "2026-03-15"
            ),
            acquired_time="0325",
            latitude=45.75,
            longitude=126.65,
            instrument="VIIRS",
            satellite="J1",
        )
    )

    assert first != second


def test_normalization_reports_rejection_reasons():
    frame = pd.DataFrame(
        [
            {
                "latitude": 45.75,
                "longitude": 126.65,
                "acq_date": "2026-03-15",
                "acq_time": 325,
                "instrument": "VIIRS",
                "satellite": "N",
                "confidence": "n",
                "version": "2.0NRT",
            },
            {
                "latitude": 999,
                "longitude": 126.65,
                "acq_date": "2026-03-15",
                "acq_time": 325,
                "instrument": "VIIRS",
                "satellite": "N",
                "confidence": "n",
                "version": "2.0NRT",
            },
            {
                "latitude": 45.75,
                "longitude": 126.65,
                "acq_date": "bad-date",
                "acq_time": 325,
                "instrument": "VIIRS",
                "satellite": "N",
                "confidence": "n",
                "version": "2.0NRT",
            },
            {
                "latitude": 45.75,
                "longitude": 126.65,
                "acq_date": "2026-03-15",
                "acq_time": 2500,
                "instrument": "VIIRS",
                "satellite": "N",
                "confidence": "n",
                "version": "2.0NRT",
            },
            {
                "latitude": 45.75,
                "longitude": 126.65,
                "acq_date": "2026-03-15",
                "acq_time": 325,
                "instrument": "VIIRS",
                "satellite": "N",
                "confidence": "l",
                "version": "2.0NRT",
            },
        ]
    )

    result = normalize_firms_dataframe(
        frame,
        firms_source="VIIRS_SNPP_NRT",
        quality_only=True,
    )

    assert result.input_rows == 5
    assert result.accepted_rows == 1
    assert result.rejected_rows == 4

    assert (
        result.rejection_counts[
            "invalid_latitude"
        ]
        == 1
    )

    assert (
        result.rejection_counts[
            "invalid_date"
        ]
        == 1
    )

    assert (
        result.rejection_counts[
            "invalid_time"
        ]
        == 1
    )

    assert (
        result.rejection_counts[
            "quality_rejected"
        ]
        == 1
    )


def test_strict_processing_requires_identity_columns():
    frame = pd.DataFrame(
        [
            {
                "latitude": 45.75,
                "longitude": 126.65,
                "acq_date": "2026-03-15",
            }
        ]
    )

    with pytest.raises(
        ValueError
    ) as exc_info:
        normalize_firms_dataframe(
            frame,
            firms_source="test",
            quality_only=True,
        )

    message = str(
        exc_info.value
    )

    assert "acq_time" in message
    assert "instrument" in message
    assert "satellite" in message
    assert "confidence" in message