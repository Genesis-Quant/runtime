"""定义手续费与策略参数敏感性分析请求。"""

import json
import math
from enum import StrEnum
from numbers import Real
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..backtest.schema import BacktestParameters


class SensitivityAnalysisType(StrEnum):
    """敏感性分析类型。"""

    FEE_ANALYSIS = "fee_analysis"
    PARAMETER_SENSITIVITY = "sensitivity"


class SensitivityCase(BaseModel):
    """一次复用共享数据执行的完整策略参数与手续费。"""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    params: dict[str, Any]
    commission: float = Field(ge=0, le=1, allow_inf_nan=False)

    @field_validator("params")
    @classmethod
    def validate_params(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name, item in value.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("case.params 不能包含空参数名")
            if item is not None and not isinstance(item, (str, int, float, bool)):
                raise ValueError(f"case.params[{name!r}] 只能是简单 JSON 值")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError(f"case.params[{name!r}] 不能是 NaN 或正负无穷")
        return value


class SensitivitySettings(BaseModel):
    """不包含策略源码的敏感性分析设置。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    analysis_type: SensitivityAnalysisType = Field(strict=False)
    cases: list[SensitivityCase] = Field(min_length=1, max_length=100)


class SensitivityParameters(BacktestParameters, SensitivitySettings):
    """在共享回测数据上执行全部敏感性组合的完整请求。"""

    @model_validator(mode="after")
    def validate_sensitivity_contract(self) -> "SensitivityParameters":
        base_commission = float(self.config["commission"])
        base_names = set(self.params)
        identities: set[str] = set()
        for number, case in enumerate(self.cases, start=1):
            if set(case.params) != base_names:
                raise ValueError(f"cases[{number}] 的 params 字段必须与来源版本完全一致")
            for name, base_value in self.params.items():
                validate_parameter_type(name, base_value, case.params[name])
            identity = json.dumps(
                {"params": case.params, "commission": case.commission},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if identity in identities:
                raise ValueError(f"cases[{number}] 与前面的分析组合重复")
            identities.add(identity)

        if self.analysis_type == SensitivityAnalysisType.FEE_ANALYSIS:
            if any(case.params != self.params for case in self.cases):
                raise ValueError("手续费分析只能修改 commission")
        elif any(case.commission != base_commission for case in self.cases):
            raise ValueError("参数敏感性分析只能修改 params")
        return self


def validate_parameter_type(name: str, base_value: Any, value: Any) -> None:
    """保证敏感性取值不会改变策略参数的基本类型。"""
    if base_value is None or value is None:
        return
    if isinstance(base_value, bool):
        valid = isinstance(value, bool)
    elif isinstance(base_value, Real) and not isinstance(base_value, bool):
        valid = isinstance(value, Real) and not isinstance(value, bool)
    else:
        valid = type(value) is type(base_value)
    if not valid:
        raise ValueError(
            f"case.params[{name!r}] 的类型必须与来源版本一致："
            f"{type(base_value).__name__}"
        )


__all__ = [
    "SensitivityAnalysisType",
    "SensitivityCase",
    "SensitivityParameters",
    "SensitivitySettings",
]
