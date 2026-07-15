"""unary.ffill 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryFfillParams(StrictModel):
    """unary.ffill 参数。"""

    limit: int | None = Field(default=None, ge=1, description="最多连续填充数量；NULL 表示不限。")


class TimeSeriesUnaryFfillOperator(TimeSeriesOperator):
    """按股票执行 ffill。"""

    op: Literal['unary.ffill'] = Field(..., description='按股票执行 ffill。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryFfillParams = Field(
        default_factory=TimeSeriesUnaryFfillParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_ffill(col, limit) {
            /*
            使用此前最近的非 NULL 值向后填充缺失值。

            每段连续 NULL 使用此前最近的非 NULL 值填充。limit 只限制单段连续 NULL 最多填充多少个位置。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            limit : int or NULL, default NULL
                每段连续 NULL 最多填充的数量；NULL 表示不限制。

            Returns
            -------
            result : vector
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> col = 1.0 2.0 3.0 4.0 5.0 6.0
            >>> col[1 2 4] = NULL

            不限制连续填充数量：
            >>> ts_unary_ffill(col, int(NULL))
            [1, 1, 1, 4, 4, 6]

            最多连续填充 1 个 NULL：
            >>> ts_unary_ffill(col, 1)
            [1, 1, NULL, 4, 4, 6]

            最多连续填充 2 个 NULL：
            >>> ts_unary_ffill(col, 2)
            [1, 1, 1, 4, 4, 6]
            */
            if (isNull(limit)) return ffill(col)
            return ffill(col, int(limit))
        }
        """
    )
