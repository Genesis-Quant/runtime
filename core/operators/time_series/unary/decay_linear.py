"""unary.decay_linear 算符模型。"""

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


class TimeSeriesUnaryDecayLinearParams(StrictModel):
    """unary.decay_linear 参数。"""

    window: int = Field(..., ge=1, description="on=true 序列中的窗口长度。")
    min_periods: int | None = Field(default=None, ge=1, description="产生结果所需的最少非空观测数。")

    @model_validator(mode="after")
    def validate_min_periods(self) -> "TimeSeriesUnaryDecayLinearParams":
        """确保最少观测数不超过窗口。"""
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError("params.min_periods 不能大于 params.window")
        return self


class TimeSeriesUnaryDecayLinearOperator(TimeSeriesOperator):
    """按股票执行 decay_linear。"""

    op: Literal['unary.decay_linear'] = Field(..., description='按股票执行 decay_linear。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryDecayLinearParams = Field(
        default_factory=TimeSeriesUnaryDecayLinearParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_decay_linear(col, window, min_periods) {
            /*
            使用线性递增权重计算滚动平均。

            窗口内从最早到最新的观测依次使用 1, 2, ..., window 的权重；NULL 对应的权重不进入分子和分母。该算符只计算完整窗口，
            因此前 window - 1 个位置始终为 NULL。min_periods 控制完整窗口内至少需要多少个非 NULL 观测。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            window : int
                正整数窗口长度。窗口包含当前位置以及此前 window - 1 个观测。
            min_periods : int or NULL, default NULL
                完整窗口内产生结果所需的最少非 NULL 观测数。NULL 表示使用 window；必须满足 1 <= min_periods <= window。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：加权窗口平均跳过 NULL，并对剩余有效权重重新归一化；有效观测少于 min_periods 时返回
            NULL。

            权重语义：窗口内权重从最旧观测的 1 线性增加到当前观测的 window，窗口右对齐；min_periods 为
            NULL 时要求完整窗口。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            三期窗口，最新观测权重最大：
            >>> ts_unary_decay_linear(col, 3, 1)
            [NULL, NULL, 2.83333, 3.16667, 4.16667, 5.66667, 6.16667, 7.16667]

            min_periods=NULL 要求完整窗口内没有 NULL：
            >>> ts_unary_decay_linear(col, 3, int(NULL))
            [NULL, NULL, 2.83333, 3.16667, 4.16667, 5.66667, 6.16667, 7.16667]

            两期窗口使用 1:2 权重：
            >>> ts_unary_decay_linear(col, 2, 2)
            [NULL, 1.66667, 3.33333, 3.33333, 4.33333, 6.33333, 6.33333, 7.33333]

            完整窗口中存在 NULL 时，剩余有效权重重新归一化：
            >>> ts_unary_decay_linear(1.0 NULL 4.0 3.0 5.0, 3, 2)
            [NULL, NULL, 3.25, 3.4, 4.16667]
            */
            minimum = rolling_min_periods(window, min_periods)
            return mavg(col, double(1..int(window)), minimum)
        }
        """,
        dependencies=(ROLLING_MIN_PERIODS,)
    )
