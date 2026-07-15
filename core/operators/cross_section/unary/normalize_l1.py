"""unary.normalize_l1 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryNormalizeL1Params(StrictModel):
    """unary.normalize_l1 不接收参数。"""


class CrossSectionUnaryNormalizeL1Operator(CrossSectionOperator):
    """按交易日执行 normalize_l1。"""

    op: Literal['unary.normalize_l1'] = Field(..., description='按交易日执行 normalize_l1。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryNormalizeL1Params = Field(
        default_factory=CrossSectionUnaryNormalizeL1Params,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_normalize_l1(col) {
            /*
            用绝对值之和缩放当前截面，使 L1 范数为 1。

            分母为当前截面的绝对值之和。分母为 0 或 NULL 时整个结果返回 NULL；原输入中的 NULL 位置保持 NULL。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_unary_normalize_l1(col)
            [0.0588235, 0.117647, 0.117647, 0.235294, 0.470588]
            */
            denominator = sum(abs(col))
            return iif(isNull(denominator) || denominator == 0, NULL, col / denominator)
        }
        """
    )
