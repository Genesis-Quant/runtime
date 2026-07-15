"""binary.rolling_cov 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    ROLLING_MIN_PERIODS,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryRollingCovParams(StrictModel):
    """binary.rolling_cov 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesBinaryRollingCovParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesBinaryRollingCovOperator(TimeSeriesOperator):
    """按股票执行 rolling_cov。"""

    op: Literal['binary.rolling_cov'] = Field(..., description='按股票执行 rolling_cov。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryRollingCovParams = Field(
        default_factory=TimeSeriesBinaryRollingCovParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_rolling_cov(left, right, window, min_periods) {
            /*
            计算两个序列的滚动样本协方差。

            窗口右对齐，当前位置使用当前观测及其前 window - 1 个观测。min_periods 为 NULL 时等于 window；有效观测不足时返回 NULL。

            Parameters
            ----------
            left : vector
                左操作数。
            right : vector
                右操作数。
            window : int
                正整数窗口长度。窗口包含当前位置以及此前 window - 1 个观测。
            min_periods : int or NULL, default NULL
                窗口内产生结果所需的最少非 NULL 观测数。NULL 表示使用 window；必须满足 1 <= min_periods <= window。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5

            min_periods=NULL 时要求完整窗口：
            >>> ts_binary_rolling_cov(left, right, 3, int(NULL))
            [NULL, NULL, 0.25, 0.375, 0.458333, 0.291667, 0.25, 0.25]

            min_periods=1 时首个有效观测即可产生结果：
            >>> ts_binary_rolling_cov(left, right, 3, 1)
            [NULL, 0.375, 0.25, 0.375, 0.458333, 0.291667, 0.25, 0.25]

            min_periods=2：
            >>> ts_binary_rolling_cov(left, right, 3, 2)
            [NULL, 0.375, 0.25, 0.375, 0.458333, 0.291667, 0.25, 0.25]

            扩大到 4 期窗口：
            >>> ts_binary_rolling_cov(left, right, 4, 2)
            [NULL, 0.375, 0.25, 0.708333, 0.5, 0.916667, 0.291667, 0.583333]
            */
            minimum = rolling_min_periods(window, min_periods)
            return mcovar(left, right, int(window), minimum)
        }
        """,
        dependencies=(ROLLING_MIN_PERIODS,)
    )
