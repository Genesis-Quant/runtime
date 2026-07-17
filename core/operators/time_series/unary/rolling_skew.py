"""unary.rolling_skew 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    ROLLING_MIN_PERIODS,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryRollingSkewParams(StrictModel):
    """unary.rolling_skew 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesUnaryRollingSkewParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesUnaryRollingSkewOperator(TimeSeriesOperator):
    """按股票执行 rolling_skew。"""

    op: Literal['unary.rolling_skew'] = Field(..., description='按股票执行 rolling_skew。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryRollingSkewParams = Field(
        default_factory=TimeSeriesUnaryRollingSkewParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_rolling_skew(col, window, min_periods) {
            /*
            计算窗口偏度。

            窗口右对齐，当前位置使用当前观测及其前 window - 1 个观测。min_periods 为 NULL 时等于 window；有效观测不足时返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            window : int
                正整数窗口长度。窗口包含当前位置以及此前 window - 1 个观测。
            min_periods : int or NULL, default NULL
                窗口内产生结果所需的最少非 NULL 观测数。NULL 表示使用 window；必须满足 1 <= min_periods <= window。

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
            >>> ts_unary_rolling_skew(col, 3, int(NULL))
            [NULL, NULL, 0.381802, 0, 0, 0, 0, 0]

            min_periods=1 时首个有效观测即可产生结果：
            >>> ts_unary_rolling_skew(col, 3, 1)
            [NULL, 0, 0.381802, 0, 0, 0, 0, 0]

            min_periods=2：
            >>> ts_unary_rolling_skew(col, 3, 2)
            [NULL, 0, 0.381802, 0, 0, 0, 0, 0]

            扩大到 4 期窗口：
            >>> ts_unary_rolling_skew(col, 4, 2)
            [NULL, 0, 0.381802, 0, 0, 0.434651, -0.434651, 0]
            */
            minimum = rolling_min_periods(window, min_periods)
            return mskew(col, int(window), true, minimum)
        }
        """,
        dependencies=(ROLLING_MIN_PERIODS,)
    )
