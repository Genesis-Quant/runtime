"""unary.bfill 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryBfillParams(StrictModel):
    """unary.bfill 参数。"""

    limit: int | None = Field(default=None, ge=1, description="最多连续填充数量；NULL 表示不限。")


class TimeSeriesUnaryBfillOperator(TimeSeriesOperator):
    """按股票执行 bfill。"""

    op: Literal['unary.bfill'] = Field(..., description='按股票执行 bfill。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryBfillParams = Field(
        default_factory=TimeSeriesUnaryBfillParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_bfill(col, limit) {
            /*
            使用后续非 NULL 值向前填充缺失值。

            每段连续 NULL 使用后续最近的非 NULL 值填充。limit 只限制单段连续 NULL 最多填充多少个位置。

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

            Notes
            -----
            NULL 处理：使用后一个非 NULL 值填充连续缺失位置；没有可用来源的边界 NULL 保持不变。limit 为
            NULL 时不限制连续填充数量。

            限制语义：limit 只限制每段连续 NULL 可填充的个数，不限制整条序列的累计填充次数；非 NULL
            原值不会被修改。

            Examples
            --------
            >>> col = 1.0 2.0 3.0 4.0 5.0 6.0
            >>> col[1 2 4] = NULL

            不限制连续填充数量：
            >>> ts_unary_bfill(col, int(NULL))
            [1, 4, 4, 4, 6, 6]

            最多连续填充 1 个 NULL：
            >>> ts_unary_bfill(col, 1)
            [1, NULL, 4, 4, 6, 6]

            最多连续填充 2 个 NULL：
            >>> ts_unary_bfill(col, 2)
            [1, 4, 4, 4, 6, 6]
            */
            if (isNull(limit)) return bfill(col)
            return bfill(col, int(limit))
        }
        """
    )
