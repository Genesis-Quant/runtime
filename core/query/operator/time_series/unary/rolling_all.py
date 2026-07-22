"""unary.rolling_all 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    ROLLING_MIN_PERIODS,
    ROLLING_TRUE_COUNT,
)

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryRollingAllParams(StrictModel):
    """unary.rolling_all 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesUnaryRollingAllParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesUnaryRollingAllOperator(TimeSeriesOperator):
    """按股票执行 rolling_all。"""

    op: Literal['unary.rolling_all'] = Field(..., description='按股票执行 rolling_all。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryRollingAllParams = Field(
        default_factory=TimeSeriesUnaryRollingAllParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_rolling_all(col, window, min_periods) {
            /*
            判断窗口内所有有效布尔观测是否均为 true。

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
            result : vector[BOOL]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：BOOL NULL 不计入有效观测分母；所有有效观测均为 true 且有效数量达到
            min_periods 时返回 true。

            窗口边界：窗口右对齐并包含当前位置；min_periods 为 NULL 时要求完整 window
            个有效观测，window 和 min_periods 均按观测行数而非日期跨度解释。

            Examples
            --------
            >>> col = false true true false true true true false

            min_periods=NULL 时要求完整窗口：
            >>> ts_unary_rolling_all(col, 3, int(NULL))
            [false, false, false, false, false, false, true, false]

            min_periods=1 时首个有效观测即可产生结果：
            >>> ts_unary_rolling_all(col, 3, 1)
            [false, false, false, false, false, false, true, false]

            min_periods=2：
            >>> ts_unary_rolling_all(col, 3, 2)
            [false, false, false, false, false, false, true, false]

            扩大到 4 期窗口：
            >>> ts_unary_rolling_all(col, 4, 2)
            [false, false, false, false, false, false, false, false]
            */
            minimum = rolling_min_periods(window, min_periods)
            count_true = rolling_true_count(col, window, minimum)
            count_valid = mcount(col, int(window), minimum)
            return (count_valid >= minimum) && (count_true == count_valid)
        }
        """,
        dependencies=(ROLLING_MIN_PERIODS, ROLLING_TRUE_COUNT)
    )
