"""unary.rolling_quantile 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    ROLLING_MIN_PERIODS,
)

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryRollingQuantileParams(StrictModel):
    """unary.rolling_quantile 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")
    q: float = Field(..., ge=0, le=1, allow_inf_nan=False, description="目标分位数。")

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesUnaryRollingQuantileParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesUnaryRollingQuantileOperator(TimeSeriesOperator):
    """按股票计算滚动分位数。"""

    op: Literal['unary.rolling_quantile'] = Field(..., description='按股票计算滚动分位数。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryRollingQuantileParams = Field(
        default_factory=TimeSeriesUnaryRollingQuantileParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_rolling_quantile(col, window, min_periods, q) {
            /*
            计算窗口分位数。

            窗口右对齐，当前位置使用当前观测及其前 window - 1 个观测。min_periods 为 NULL 时等于 window；有效观测不足时返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            window : int
                正整数窗口长度。窗口包含当前位置以及此前 window - 1 个观测。
            min_periods : int or NULL, default NULL
                窗口内产生结果所需的最少非 NULL 观测数。NULL 表示使用 window；必须满足 1 <= min_periods <= window。
            q : float
                目标分位数，取值范围为 [0, 1]。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：窗口聚合跳过 NULL，min_periods 按窗口内非 NULL
            数量判断；达到门槛后，当前位置为 NULL 也可能由同一窗口的其他有效观测产生结果。

            窗口边界：窗口右对齐并包含当前位置；min_periods 为 NULL 时要求完整 window
            个有效观测，window 和 min_periods 均按观测行数而非日期跨度解释。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            min_periods=NULL 时要求完整窗口：
            >>> ts_unary_rolling_quantile(col, 3, int(NULL), 0.5)
            [NULL, NULL, 2, 3, 4, 5, 6, 7]

            min_periods=1 时首个有效观测即可产生结果：
            >>> ts_unary_rolling_quantile(col, 3, 1, 0.5)
            [1, 1.5, 2, 3, 4, 5, 6, 7]

            min_periods=2：
            >>> ts_unary_rolling_quantile(col, 3, 2, 0.5)
            [NULL, 1.5, 2, 3, 4, 5, 6, 7]

            扩大到 4 期窗口：
            >>> ts_unary_rolling_quantile(col, 4, 2, 0.5)
            [NULL, 1.5, 2, 2.5, 3.5, 4.5, 5.5, 6.5]

            25% 分位数：
            >>> ts_unary_rolling_quantile(col, 3, 2, 0.25)
            [NULL, 1.25, 1.5, 2.5, 3.5, 4, 5.5, 6.5]

            75% 分位数：
            >>> ts_unary_rolling_quantile(col, 3, 2, 0.75)
            [NULL, 1.75, 3, 3.5, 4.5, 6, 6.5, 7.5]
            */
            minimum = rolling_min_periods(window, min_periods)
            return mpercentile(col, 100 * q, int(window), "linear", minimum)
        }
        """,
        dependencies=(ROLLING_MIN_PERIODS,)
    )
