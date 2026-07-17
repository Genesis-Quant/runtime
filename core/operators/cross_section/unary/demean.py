"""unary.demean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryDemeanParams(StrictModel):
    """unary.demean 不接收参数。"""


class CrossSectionUnaryDemeanOperator(CrossSectionOperator):
    """按交易日执行 demean。"""

    op: Literal['unary.demean'] = Field(..., description='按交易日执行 demean。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryDemeanParams = Field(
        default_factory=CrossSectionUnaryDemeanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_demean(col) {
            /*
            从每个有效观测中减去当前截面均值。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：截面均值忽略 NULL，但原输入为 NULL 的位置在减法后仍为 NULL；全 NULL
            截面没有可用均值。

            数值语义：只移除截面均值，不除以尺度；有效残差之和仅受浮点舍入误差影响，理论上为 0。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_unary_demean(col)
            [-2.4, -1.4, -1.4, 0.6, 4.6]

            均值跳过 NULL，但缺失位置仍缺失：
            >>> cs_unary_demean(double([1, NULL, 3]))
            [-1, NULL, 1]
            */
            return col - avg(col)
        }
        """
    )
