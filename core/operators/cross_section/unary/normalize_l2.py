"""unary.normalize_l2 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryNormalizeL2Params(StrictModel):
    """unary.normalize_l2 不接收参数。"""


class CrossSectionUnaryNormalizeL2Operator(CrossSectionOperator):
    """按交易日执行 normalize_l2。"""

    op: Literal['unary.normalize_l2'] = Field(..., description='按交易日执行 normalize_l2。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryNormalizeL2Params = Field(
        default_factory=CrossSectionUnaryNormalizeL2Params,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_normalize_l2(col) {
            /*
            用平方和的平方根缩放当前截面，使 L2 范数为 1。

            分母为当前截面的平方和的平方根。分母为 0 或 NULL 时整个结果返回 NULL；原输入中的 NULL 位置保持 NULL。

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
            NULL 处理：分母按有效值平方和的平方根计算并忽略 NULL，原输入为 NULL 的位置仍为 NULL；分母为 0
            或无有效值时整个截面返回 NULL。

            归一化语义：有效结果的平方和为 1，不执行中心化。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_unary_normalize_l2(col)
            [0.106, 0.212, 0.212, 0.423999, 0.847998]

            分母忽略 NULL，缺失位置保持 NULL：
            >>> isNull(cs_unary_normalize_l2(double([1, NULL, 3])))
            [false, true, false]
            */
            denominator = sqrt(sum(col * col))
            return iif(isNull(denominator) || denominator == 0, NULL, col / denominator)
        }
        """
    )
