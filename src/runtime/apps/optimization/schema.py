"""定义滚动回测参数调优请求。"""

import math
import re
from datetime import date
from enum import StrEnum
from functools import reduce
from numbers import Integral, Real
from operator import mul
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runtime.utils import normalize_date_range

from ..backtest.schema import BacktestParameters

ROLLING_PERIOD_PATTERN = re.compile(r"^(?:P)?([1-9]\d*)([DWMY])$", re.IGNORECASE)


class OptimizationAlgorithm(StrEnum):
    """有限参数池上可使用的调优算法。"""

    RANDOM_SEARCH = "random_search"
    LATIN_HYPERCUBE = "latin_hypercube"
    HALTON = "halton"
    MAXIMIN = "maximin"
    HILL_CLIMB = "hill_climb"
    COORDINATE_DESCENT = "coordinate_descent"
    PATTERN_SEARCH = "pattern_search"
    TABU_SEARCH = "tabu_search"
    SIMULATED_ANNEALING = "simulated_annealing"
    THRESHOLD_ACCEPTING = "threshold_accepting"
    GREAT_DELUGE = "great_deluge"
    DIFFERENTIAL_EVOLUTION = "differential_evolution"
    PARTICLE_SWARM = "particle_swarm"
    GENETIC_ALGORITHM = "genetic_algorithm"
    EVOLUTION_STRATEGY = "evolution_strategy"
    CROSS_ENTROPY = "cross_entropy"
    TPE = "tpe"
    RBF_SURROGATE = "rbf_surrogate"
    KNN_UCB = "knn_ucb"
    ADAPTIVE_RANDOM = "adaptive_random"


class WalkForwardWindow(BaseModel):
    """一个样本内训练区间及其紧随的样本外持有区间。"""

    model_config = ConfigDict(frozen=True, strict=True)

    number: int = Field(ge=1)
    training_start: date
    training_end: date
    holding_start: date
    holding_end: date

    @model_validator(mode="after")
    def validate_dates(self) -> "WalkForwardWindow":
        if self.training_start > self.training_end:
            raise ValueError("training_start 不能晚于 training_end")
        if self.holding_start > self.holding_end:
            raise ValueError("holding_start 不能晚于 holding_end")
        if self.training_end >= self.holding_start:
            raise ValueError("训练区间必须早于样本外持有区间")
        return self


class OptimizationSelection(BaseModel):
    """一次调优选择的初始点、最终点和已评价点。"""

    model_config = ConfigDict(frozen=True, strict=True)

    initial_index: int = Field(ge=0)
    selected_index: int = Field(ge=0)
    evaluated_indices: tuple[int, ...]
    selected_score: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_indices(self) -> "OptimizationSelection":
        if len(self.evaluated_indices) != len(set(self.evaluated_indices)):
            raise ValueError("evaluated_indices 不能重复")
        if self.initial_index not in self.evaluated_indices:
            raise ValueError("initial_index 必须包含在 evaluated_indices 中")
        if self.selected_index not in self.evaluated_indices:
            raise ValueError("selected_index 必须包含在 evaluated_indices 中")
        return self


class OptimizationSettings(BaseModel):
    """不包含策略源码的滚动调优设置。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    parameter_space: dict[str, list[int | float]] = Field(min_length=1)
    algorithms: list[OptimizationAlgorithm] = Field(min_length=1)
    start_date: str
    end_date: str
    lookback_period: str = Field(description="每个样本外窗口使用的历史训练长度，例如 6M。")
    holding_period: str = Field(description="每组最终参数连续运行的样本外长度，例如 2W。")
    repetitions: int = Field(default=1, ge=1, le=100)
    evaluation_budget: int = Field(default=12, ge=2, le=100)
    seed: int = Field(default=20260815, ge=0, le=2_147_483_647)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_optimization_date(cls, value: str, info: Any) -> str:
        if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError(f"{info.field_name} 必须是 YYYY-MM-DD 格式")
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{info.field_name} 不是有效日期") from error
        return value

    @field_validator("lookback_period", "holding_period", mode="before")
    @classmethod
    def normalize_rolling_period(cls, value: Any, info: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} 必须是 D、W、M 或 Y 周期字符串")
        match = ROLLING_PERIOD_PATTERN.fullmatch(value.strip())
        if match is None:
            raise ValueError(f"{info.field_name} 必须类似 30D、2W、6M 或 1Y")
        return f"{int(match.group(1))}{match.group(2).upper()}"

    @field_validator("parameter_space", mode="before")
    @classmethod
    def validate_parameter_space_values(cls, value: Any) -> dict[str, list[int | float]]:
        if not isinstance(value, dict) or not value:
            raise ValueError("parameter_space 必须是非空数值列表字典")
        result: dict[str, list[int | float]] = {}
        for raw_name, raw_values in value.items():
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise ValueError("parameter_space 不能包含空参数名")
            name = raw_name.strip()
            if name in result:
                raise ValueError(f"parameter_space 参数名重复：{name}")
            if not isinstance(raw_values, list) or not 2 <= len(raw_values) <= 100:
                raise ValueError(f"parameter_space[{name!r}] 必须包含 2 到 100 个数值")
            values: list[int | float] = []
            seen: set[float] = set()
            for raw_value in raw_values:
                if isinstance(raw_value, bool) or not isinstance(raw_value, Real):
                    raise ValueError(f"parameter_space[{name!r}] 只能包含整数或浮点数")
                numeric = float(raw_value)
                if not math.isfinite(numeric):
                    raise ValueError(f"parameter_space[{name!r}] 不能包含 NaN 或正负无穷")
                if numeric in seen:
                    raise ValueError(f"parameter_space[{name!r}] 不能包含重复值")
                seen.add(numeric)
                values.append(int(raw_value) if isinstance(raw_value, Integral) else numeric)
            result[name] = values
        return result

    @field_validator("algorithms", mode="before")
    @classmethod
    def validate_algorithms(cls, value: Any) -> list[OptimizationAlgorithm]:
        if not isinstance(value, list):
            raise ValueError("algorithms 必须是调优算法名称列表")
        try:
            result = [OptimizationAlgorithm(item) for item in value]
        except (TypeError, ValueError) as error:
            choices = [algorithm.value for algorithm in OptimizationAlgorithm]
            raise ValueError(f"algorithms 只支持：{choices}") from error
        if len(result) != len(set(result)):
            raise ValueError("algorithms 不能重复")
        return result

    @model_validator(mode="after")
    def validate_date_range(self) -> "OptimizationSettings":
        normalize_date_range(self.start_date, self.end_date)
        return self


class OptimizationParameters(BacktestParameters, OptimizationSettings):
    """滚动样本内调优并拼接样本外净值路径的完整请求。"""

    @model_validator(mode="after")
    def validate_optimization_contract(self) -> "OptimizationParameters":
        missing = sorted(set(self.parameter_space) - set(self.params))
        if missing:
            raise ValueError(f"parameter_space 只能选择 params 已定义的参数：{missing}")
        for name in self.parameter_space:
            value = self.params[name]
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"params[{name!r}] 必须是数值")
        combination_count = reduce(mul, (len(values) for values in self.parameter_space.values()), 1)
        if combination_count > 100_000:
            raise ValueError("parameter_space 的参数组合不能超过 100000 个")
        return self


__all__ = [
    "OptimizationAlgorithm",
    "OptimizationParameters",
    "OptimizationSettings",
]
