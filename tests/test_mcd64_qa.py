# Day5A：MCD64A1 QA位解码与烧毁候选像元质量规则测试

import pytest

from fire_monitor.core.mcd64_qa import (
    decode_mcd64_qa,
    evaluate_burned_candidate_qa,
)


def test_decode_standard_valid_land_pixel():
    decoded = decode_mcd64_qa(
        3
    )

    assert decoded.raw_value == 3
    assert decoded.is_land is True
    assert (
        decoded.has_valid_data
        is True
    )
    assert (
        decoded
        .shortened_mapping_period
        is False
    )
    assert (
        decoded
        .contextually_relabeled
        is False
    )
    assert (
        decoded.spare_bit_set
        is False
    )
    assert (
        decoded
        .special_condition_code
        == 0
    )


def test_standard_policy_accepts_clean_pixel():
    result = (
        evaluate_burned_candidate_qa(
            3,
            policy="standard",
        )
    )

    assert result.accepted is True
    assert result.reasons == ()
    assert result.warnings == ()


def test_standard_policy_keeps_shortened_period_with_warning():
    # 7 = bit0 + bit1 + bit2
    result = (
        evaluate_burned_candidate_qa(
            7,
            policy="standard",
        )
    )

    assert result.accepted is True

    assert any(
        "shortened" in warning
        for warning
        in result.warnings
    )


def test_strict_policy_rejects_shortened_period():
    result = (
        evaluate_burned_candidate_qa(
            7,
            policy="strict",
        )
    )

    assert result.accepted is False

    assert any(
        "shortened" in reason
        for reason
        in result.reasons
    )


def test_water_or_invalid_data_is_rejected():
    water = (
        evaluate_burned_candidate_qa(
            0
        )
    )

    no_valid_data = (
        evaluate_burned_candidate_qa(
            1
        )
    )

    assert water.accepted is False
    assert (
        no_valid_data.accepted
        is False
    )

    assert any(
        "水体" in reason
        for reason
        in water.reasons
    )

    assert any(
        "有效数据不足" in reason
        for reason
        in no_valid_data.reasons
    )


def test_special_condition_is_rejected_for_burned_candidate():
    # 35 =
    # bit0 land
    # bit1 valid
    # bits5-7 special condition = 1
    result = (
        evaluate_burned_candidate_qa(
            35
        )
    )

    assert result.accepted is False

    assert (
        result.decoded
        .special_condition_code
        == 1
    )


def test_contextual_relabeling_is_kept_as_warning():
    # 11 = bit0 + bit1 + bit3
    result = (
        evaluate_burned_candidate_qa(
            11
        )
    )

    assert result.accepted is True

    assert any(
        "relabeling" in warning
        for warning
        in result.warnings
    )


def test_invalid_qa_values_are_rejected():
    with pytest.raises(
        ValueError
    ):
        decode_mcd64_qa(-1)

    with pytest.raises(
        ValueError
    ):
        decode_mcd64_qa(256)

    with pytest.raises(
        ValueError
    ):
        decode_mcd64_qa(3.5)

    with pytest.raises(
        ValueError
    ):
        decode_mcd64_qa("bad")