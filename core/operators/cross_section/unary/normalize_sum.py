"""unary.normalize_sum 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryNormalizeSumParams(StrictModel):
    """unary.normalize_sum 不接收参数。"""


class CrossSectionUnaryNormalizeSumOperator(CrossSectionOperator):
    """按交易日执行 normalize_sum。"""

    op: Literal['unary.normalize_sum'] = Field(..., description='按交易日执行 normalize_sum。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryNormalizeSumParams = Field(
        default_factory=CrossSectionUnaryNormalizeSumParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_normalize_sum(col) {
            /*
            用总和缩放当前截面，使有效值之和为 1。

            分母为当前截面的有效值总和。分母为 0 或 NULL 时整个结果返回 NULL；原输入中的 NULL 位置保持 NULL。

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
            NULL 处理：分母按有效值之和计算并忽略 NULL，原输入为 NULL 的位置仍为 NULL；分母为 0
            或无有效值时整个截面返回 NULL。

            归一化语义：正负值可能相互抵消，因此存在非零观测时总和仍可能为 0。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_unary_normalize_sum(col)
            [0.0588235, 0.117647, 0.117647, 0.235294, 0.470588]

            分母忽略 NULL，缺失位置保持 NULL：
            >>> cs_unary_normalize_sum(double([1, NULL, 3]))
            [0.25, NULL, 0.75]
            */
            denominator = sum(col)
            return iif(isNull(denominator) || denominator == 0, NULL, col / denominator)
        }
        """
    )
