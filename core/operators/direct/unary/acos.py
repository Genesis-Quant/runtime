"""unary.acos 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryAcosParams(StrictModel):
    """unary.acos 不接收参数。"""


class DirectUnaryAcosOperator(DirectOperator):
    """逐行执行 acos。"""

    op: Literal['unary.acos'] = Field(..., description='逐行执行 acos。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryAcosParams = Field(
        default_factory=DirectUnaryAcosParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_acos(col) {
            /*
            逐元素计算反余弦，输入值必须位于 [-1, 1]。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Examples
            --------
            >>> col = -1.0 -0.5 0.0 0.5 1.0
            >>> direct_unary_acos(col)
            [3.14159, 2.0944, 1.5708, 1.0472, 0]
            */
            return acos(col)
        }
        """
    )
