"""unary.expanding_sem 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    MASK_EXPANDING_RESULT,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryExpandingSemParams(StrictModel):
    """unary.expanding_sem 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesUnaryExpandingSemOperator(TimeSeriesOperator):
    """按股票执行 expanding_sem。"""

    op: Literal['unary.expanding_sem'] = Field(..., description='按股票执行 expanding_sem。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryExpandingSemParams = Field(
        default_factory=TimeSeriesUnaryExpandingSemParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_expanding_sem(col, min_periods) {
            /*
            计算从序列起点到当前位置的均值标准误。

            第 i 个结果使用从序列首个观测到第 i 个观测的全部历史。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            min_periods : int, default 1
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：累计统计忽略 NULL，min_periods 按非 NULL 观测数判断；达到门槛后，当前输入为
            NULL 也可能返回已有历史形成的统计值。

            扩展窗口：每个位置使用从序列起点到当前位置的全部历史，旧观测不会滚出窗口。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            min_periods=1：
            >>> ts_unary_expanding_sem(col, 1)
            [NULL, 0.5, 0.881917, 0.645497, 0.707107, 0.881917, 0.816497, 0.866025]

            min_periods=3：
            >>> ts_unary_expanding_sem(col, 3)
            [NULL, NULL, 0.881917, 0.645497, 0.707107, 0.881917, 0.816497, 0.866025]

            min_periods=5：
            >>> ts_unary_expanding_sem(col, 5)
            [NULL, NULL, NULL, NULL, 0.707107, 0.881917, 0.816497, 0.866025]
            */
            result = cumstd(col) / sqrt(cumcount(col))
            return mask_expanding_result(result, col, min_periods)
        }
        """,
        dependencies=(MASK_EXPANDING_RESULT,)
    )
