"""MCD64A1 QA 位解码与烧毁候选像元质量判断。

本模块只解释 MCD64A1 V6.1 QA 字段，并实现平台当前采用的
烧毁候选像元质量策略。

官方 QA 位定义：
bit 0   land / water
bit 1   valid data
bit 2   shortened mapping period
bit 3   contextual relabeling
bit 4   spare，正常应为 0
bits 5-7 special condition code

注意：
这里的 standard / strict 是本平台的数据处理策略，
不是 NASA 强制规定的唯一筛选方式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_QA_POLICIES = {
    "standard",
    "strict",
}


@dataclass(frozen=True)
class Mcd64QaDecoded:
    """一个 MCD64A1 QA byte 的解码结果。"""

    raw_value: int
    is_land: bool
    has_valid_data: bool
    shortened_mapping_period: bool
    contextually_relabeled: bool
    spare_bit_set: bool
    special_condition_code: int


@dataclass(frozen=True)
class Mcd64QaDecision:
    """烧毁候选像元的 QA 判断结果。"""

    accepted: bool
    policy: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    decoded: Mcd64QaDecoded


def _as_qa_byte(
    value: Any,
) -> int:
    """将输入值规范化为 0-255 的整数 QA byte。"""

    if value is None:
        raise ValueError(
            "MCD64A1 QA 值不能为空。"
        )

    try:
        numeric = float(value)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "MCD64A1 QA 值必须是整数。"
        ) from exc

    if not numeric.is_integer():
        raise ValueError(
            "MCD64A1 QA 值必须是整数。"
        )

    raw = int(numeric)

    if not 0 <= raw <= 255:
        raise ValueError(
            "MCD64A1 QA 值必须位于 0-255。"
        )

    return raw


def decode_mcd64_qa(
    value: Any,
) -> Mcd64QaDecoded:
    """按照 MCD64A1 V6.1 官方位定义解码 QA byte。"""

    raw = _as_qa_byte(
        value
    )

    return Mcd64QaDecoded(
        raw_value=raw,

        # bit 0
        is_land=bool(
            raw & (1 << 0)
        ),

        # bit 1
        has_valid_data=bool(
            raw & (1 << 1)
        ),

        # bit 2
        shortened_mapping_period=bool(
            raw & (1 << 2)
        ),

        # bit 3
        contextually_relabeled=bool(
            raw & (1 << 3)
        ),

        # bit 4
        spare_bit_set=bool(
            raw & (1 << 4)
        ),

        # bits 5-7
        special_condition_code=(
            raw >> 5
        ) & 0b111,
    )


def evaluate_burned_candidate_qa(
    value: Any,
    *,
    policy: str = "standard",
) -> Mcd64QaDecision:
    """判断一个 Burn Date > 0 候选像元是否通过 QA。

    standard：
    - 必须是 land；
    - 必须具有 valid data；
    - spare bit 必须为 0；
    - burned candidate 的 special condition 必须为 0；
    - shortened mapping period 只记录警告；
    - contextual relabeling 只记录信息性警告。

    strict：
    在 standard 基础上，
    shortened mapping period 也会被拒绝。
    """

    if (
        policy
        not in
        SUPPORTED_QA_POLICIES
    ):
        raise ValueError(
            f"不支持的 MCD64A1 QA 策略：{policy}"
        )

    decoded = decode_mcd64_qa(
        value
    )

    reasons: list[str] = []
    warnings: list[str] = []

    if not decoded.is_land:
        reasons.append(
            "QA 标记为水体像元"
        )

    if not decoded.has_valid_data:
        reasons.append(
            "QA 标记为有效数据不足"
        )

    if decoded.spare_bit_set:
        reasons.append(
            "QA spare bit 非零，"
            "不符合当前 MCD64A1 QA 合同"
        )

    # 官方说明 bits 5-7 的特殊条件代码
    # 为未烧毁像元保留。
    # 对已经具有 Burn Date > 0 的候选像元，
    # 非零值视为产品内部状态不一致。
    if (
        decoded.special_condition_code
        != 0
    ):
        reasons.append(
            "烧毁候选像元存在非零"
            " special condition code"
        )

    if (
        decoded
        .shortened_mapping_period
    ):
        if policy == "strict":
            reasons.append(
                "QA 标记为 shortened "
                "mapping period"
            )
        else:
            warnings.append(
                "QA 标记为 shortened "
                "mapping period"
            )

    if (
        decoded
        .contextually_relabeled
    ):
        warnings.append(
            "像元经过 contextual relabeling"
        )

    return Mcd64QaDecision(
        accepted=not reasons,
        policy=policy,
        reasons=tuple(
            reasons
        ),
        warnings=tuple(
            warnings
        ),
        decoded=decoded,
    )