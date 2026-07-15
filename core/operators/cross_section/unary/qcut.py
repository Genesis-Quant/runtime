"""unary.qcut 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryQcutParams(StrictModel):
    """unary.qcut 参数。"""

    q: int = Field(..., ge=2, description="分箱数量。")


class CrossSectionUnaryQcutOperator(CrossSectionOperator):
    """按交易日等频分箱。"""

    op: Literal['unary.qcut'] = Field(..., description='按交易日等频分箱。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryQcutParams = Field(
        default_factory=CrossSectionUnaryQcutParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_qcut(col, q) {
            /*
            按当前截面分位数把有效观测划分为 q 个整数分箱。

            分箱编号从 0 开始，最大为 q - 1。并列值使用最小名次，因此相同值不会被拆到不同分箱。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            q : int
                分箱数量，必须至少为 2；返回编号范围为 0 到 q - 1。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            划分为 2 箱：
            >>> cs_unary_qcut(col, 2)
            [0, 0, 0, 1, 1]

            划分为 3 箱：
            >>> cs_unary_qcut(col, 3)
            [0, 0, 0, 1, 2]

            划分为 4 箱：
            >>> cs_unary_qcut(col, 4)
            [0, 0, 0, 2, 3]
            */
            return rank(col, true, int(q), true, `min, false)
        }
        """
    )
