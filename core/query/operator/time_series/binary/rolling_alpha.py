"""binary.rolling_alpha 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    ROLLING_INTERCEPT,
    ROLLING_MIN_PERIODS,
)

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryRollingAlphaParams(StrictModel):
    """binary.rolling_alpha 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesBinaryRollingAlphaParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesBinaryRollingAlphaOperator(TimeSeriesOperator):
    """按股票执行 rolling_alpha。"""

    op: Literal['binary.rolling_alpha'] = Field(..., description='按股票执行 rolling_alpha。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryRollingAlphaParams = Field(
        default_factory=TimeSeriesBinaryRollingAlphaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_rolling_alpha(left, right, window, min_periods) {
            /*
            计算滚动窗口内以 left 解释 right 的回归截距。

            窗口右对齐，当前位置使用当前观测及其前 window - 1 个观测。min_periods 为 NULL 时等于 window；有效观测不足时返回 NULL。

            回归方向固定为 right 对 left；left 是解释变量，right 是因变量。

            Parameters
            ----------
            left : vector
                回归中的解释变量向量。
            right : vector
                回归中的因变量向量。
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
            NULL 处理：二元窗口统计只使用两侧同时有效的观测；有效配对不足、解释变量零方差或当前位置无法形成残差时返回
            NULL。

            窗口边界：窗口右对齐并包含当前位置；min_periods 为 NULL 时要求完整 window
            个有效观测，window 和 min_periods 均按观测行数而非日期跨度解释。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5

            min_periods=NULL 时要求完整窗口：
            >>> ts_binary_rolling_alpha(left, right, 3, int(NULL))
            [NULL, NULL, 1.21429, 1.51923, 1.82692, 1.75, 2.64286, 2.78571]

            min_periods=1 时首个有效观测即可产生结果：
            >>> ts_binary_rolling_alpha(left, right, 3, 1)
            [NULL, 1.16667, 1.21429, 1.51923, 1.82692, 1.75, 2.64286, 2.78571]

            min_periods=2：
            >>> ts_binary_rolling_alpha(left, right, 3, 2)
            [NULL, 1.16667, 1.21429, 1.51923, 1.82692, 1.75, 2.64286, 2.78571]

            扩大到 4 期窗口：
            >>> ts_binary_rolling_alpha(left, right, 4, 2)
            [NULL, 1.16667, 1.21429, 1.17333, 1.075, 1.37333, 1.15, 2.19231]
            */
            minimum = rolling_min_periods(window, min_periods)
            return rolling_intercept(left, right, window, minimum)
        }
        """,
        dependencies=(ROLLING_INTERCEPT, ROLLING_MIN_PERIODS)
    )
