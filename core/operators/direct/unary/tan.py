"""unary.tan 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryTanParams(StrictModel):
    """unary.tan 不接收参数。"""


class DirectUnaryTanOperator(DirectOperator):
    """逐行执行 tan。"""

    op: Literal['unary.tan'] = Field(..., description='逐行执行 tan。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryTanParams = Field(
        default_factory=DirectUnaryTanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_tan(col) {
            /*
            逐元素计算正切。

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
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_tan(col)
            [0.747022, -1.55741, 0, 14.1014, 0.0584739]
            */
            return tan(col)
        }
        """
    )
