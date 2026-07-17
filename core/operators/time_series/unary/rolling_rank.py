"""unary.rolling_rank 算符模型。"""

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


class TimeSeriesUnaryRollingRankParams(StrictModel):
    """unary.rolling_rank 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")
    ascending: bool = Field(default=True, description="是否按升序排名。")
    ties_method: Literal["min", "max", "average"] = Field(
        default="min", description="并列值处理方式。"
    )

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesUnaryRollingRankParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesUnaryRollingRankOperator(TimeSeriesOperator):
    """按股票执行 rolling_rank。"""

    op: Literal['unary.rolling_rank'] = Field(..., description='按股票执行 rolling_rank。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryRollingRankParams = Field(
        default_factory=TimeSeriesUnaryRollingRankParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_rolling_rank(col, window, min_periods, ascending, ties_method) {
            /*
            计算当前值在窗口内的排名。

            窗口右对齐，当前位置使用当前观测及其前 window - 1 个观测。min_periods 为 NULL 时等于 window；有效观测不足时返回 NULL。

            每个位置只返回当前观测在其窗口中的名次，而不是整个窗口的排名向量。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            window : int
                正整数窗口长度。窗口包含当前位置以及此前 window - 1 个观测。
            min_periods : int or NULL, default NULL
                窗口内产生结果所需的最少非 NULL 观测数。NULL 表示使用 window；必须满足 1 <= min_periods <= window。
            ascending : bool, default true
                true 时最小值排名最前；false 时最大值排名最前。
            ties_method : {"min", "max", "average"}, default "min"
                并列值处理方式：
                * "min"：并列组使用该组的最小名次。
                * "max"：并列组使用该组的最大名次。
                * "average"：并列组使用所占名次的平均值。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：窗口统计忽略历史 NULL，但当前位置为 NULL 时排名为 NULL；min_periods
            按窗口内非 NULL 数量判断。

            窗口边界：窗口右对齐并包含当前位置；min_periods 为 NULL 时要求完整 window
            个有效观测，window 和 min_periods 均按观测行数而非日期跨度解释。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 3.0 2.0 4.0 4.0 5.0

            ties_method="min"：
            >>> ts_unary_rolling_rank(col, 3, 2, true, "min")
            [NULL, 2, 2, 3, 1, 3, 2, 3]

            ties_method="max"：
            >>> ts_unary_rolling_rank(col, 3, 2, true, "max")
            [NULL, 2, 3, 3, 2, 3, 3, 3]

            ties_method="average"：
            >>> ts_unary_rolling_rank(col, 3, 2, true, "average")
            [NULL, 2, 2.5, 3, 1.5, 3, 2.5, 3]

            降序排名：
            >>> ts_unary_rolling_rank(col, 3, 2, false, "min")
            [NULL, 1, 1, 1, 2, 1, 1, 1]

            min_periods=NULL 时必须先形成完整窗口：
            >>> ts_unary_rolling_rank(col, 3, int(NULL), true, "min")
            [NULL, NULL, 2, 3, 1, 3, 2, 3]

            使用更长的窗口：
            >>> ts_unary_rolling_rank(col, 4, 2, true, "min")
            [NULL, 2, 2, 4, 1, 4, 3, 4]

            窗口含 NULL 时只对有效观测排名：
            >>> ts_unary_rolling_rank(1.0 NULL 2.0 2.0 3.0, 3, 2, true, "average")
            [NULL, NULL, 2, 1.5, 3]
            */
            minimum = rolling_min_periods(window, min_periods)
            result = mrank(col, ascending, int(window), true, ties_method, false, minimum)
            if (!false) result = result + 1
            return result
        }
        """,
        dependencies=(ROLLING_MIN_PERIODS,)
    )
